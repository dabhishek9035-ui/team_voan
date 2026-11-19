"""B7. Adaptive evidence challenge.

Trigger: a claim is `needs_review` (or `insufficient`) AND a specific attribute is unresolved.
Request: the smallest extra item that would conflict with a weak claim, chosen from a plain rule table.
Response: the traveller sends an ordinary screenshot; it goes through the normal Evidence/Interpretation/Relationship chain.
No-response path: after `challenge_response_hours` the challenge becomes `no_response`. The claim stays
"unverified, needs review" and the coordinator sees the reason. NOTHING is ever auto-rejected: no Decision is written here.

Threat model (say it openly): defeats accidental omission, a single pre-made fake and simple reuse.
It does NOT stop someone who generates a full, consistent set of screenshots.
"""
from datetime import timedelta

from . import claims as cl, trust, views as vw
from .errors import ValidationError

# request type -> (human text, screenshot types that count as an answer)
REQUESTS = {
    "bank_sms": ("the bank SMS for this payment", ("BANK_SMS",)),
    "payment_history": ("a screenshot of your payment-app history list showing this payment", ("UPI_SUCCESS",)),
    "ticket_with_status_bar": ("the ticket screen with the phone status bar and time visible", ("TICKET_QR",)),
}
# reason code -> short plain reason (structured code first; Member A translates the text)
REASONS = {
    "utr_unreadable": "the transaction number could not be read",
    "amount_or_time_unreadable": "the amount or time could not be read",
    "ticket_fields_unreadable": "the ticket id or time could not be read",
    "no_ticket_seen": "no ticket has been seen for this payment",
    "no_second_source_for_payment": "no second source has been seen for this payment",
    "link_by_amount_time_only": "the payment and ticket are matched on amount and time only",
}
# unresolved signal -> (attribute, request_type, reason_code). Order = priority.
def _rule(signal, params, claim_types):
    fields = params.get("fields", "")
    if signal in ("unreadable_key_field", "low_extraction_confidence"):
        if "utr" in fields:
            return "utr", "bank_sms", "utr_unreadable"
        if "ticket_id" in fields or "qr_payload" in fields:
            return "ticket_id", "ticket_with_status_bar", "ticket_fields_unreadable"
        return "amount_or_time", "payment_history", "amount_or_time_unreadable"
    if signal == "no_counterpart":
        if params.get("missing") == "ticket":
            return "ticket_issued", "ticket_with_status_bar", "no_ticket_seen"
        return "debit", "payment_history", "no_second_source_for_payment"
    if signal == "inferred_link_only" and "BANK_SMS" not in claim_types:
        return "debit", "bank_sms", "link_by_amount_time_only"
    return None


def _iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _find_claim(store, trip_id, cfg, claim_ref, now):
    for c in cl.build_claims(store, trip_id, cfg, now):
        if c["claim_ref"] == claim_ref or c["root"] == claim_ref:
            return c
    raise ValidationError(f"no claim {claim_ref!r} on trip {trip_id!r}")


def unresolved(store, claim, cfg, trip=None):
    """Ordered list of {attribute, request_type, reason_code} for this claim. Empty = nothing to ask."""
    a = trust.assess(store, claim, cfg, trip)
    if a["decision_support"] == "clear":
        return a, []
    types = set(claim["types"].values())
    out, seen = [], set()
    for s in a["signals"]:
        r = _rule(s["code"], s["params"], types)
        if r and r not in seen:
            seen.add(r)
            out.append({"attribute": r[0], "request_type": r[1], "reason_code": r[2]})
    return a, out


def message_for(request_type, reason_code):
    what, _ = REQUESTS[request_type]
    return (f"Please send {what}. Why: {REASONS[reason_code]}. "
            "If you cannot, that is fine: nothing is rejected and your coordinator will review it.")


def issue(store, trip_id, claim_ref, cfg, now=None):
    """Issue the highest-priority challenge for a claim. Idempotent: an open one is returned, not duplicated."""
    now = now or cl.now_utc()
    trip = store.get_trip(trip_id)
    claim = _find_claim(store, trip_id, cfg, claim_ref, now)
    _, todo = unresolved(store, claim, cfg, trip)
    if not todo:
        raise ValidationError("nothing unresolved to ask for: claim is clear or has no specific unresolved attribute")
    subject = claim["root"]
    open_ = [c for c in store.current_challenges(subject_ref=subject) if c["status"] == "issued"]
    for want in todo:
        for c in open_:
            if c["attribute"] == want["attribute"]:
                return c
    pick = todo[0]
    cid = store.add_challenge(subject, trip_id, pick["attribute"], pick["request_type"], pick["reason_code"],
                              message_for(pick["request_type"], pick["reason_code"]),
                              _iso(now + timedelta(hours=cfg["challenge_response_hours"])))
    return _row(store, cid)


def _row(store, cid):
    return next(c for c in store.current_challenges() if c["challenge_id"] == cid)


def respond(store, challenge_id, response_evidence_id):
    """Mark a challenge answered by an ordinary evidence item (which has its own chain)."""
    cur = {c["challenge_id"]: c for c in store.current_challenges()}
    ch = cur.get(challenge_id)
    if ch is None:
        raise ValidationError(f"no open challenge row {challenge_id!r} (unknown or already superseded)")
    if ch["status"] != "issued":
        raise ValidationError(f"challenge is already {ch['status']}")
    store.get(response_evidence_id)
    nid = store.add_challenge(ch["subject_ref"], ch["trip_id"], ch["attribute"], ch["request_type"],
                              ch["reason_code"], ch["message"], ch["due_at"], status="responded",
                              response_evidence_id=response_evidence_id, supersedes=challenge_id)
    return _row(store, nid)


def auto_respond(store, trip_id, cfg):
    """Match issued challenges to later evidence from the same traveller of an accepted screenshot type."""
    done = []
    its = vw.items(store, trip_id)
    for ch in store.current_challenges(trip_id=trip_id):
        if ch["status"] != "issued":
            continue
        root = next((i for i in its if i["id"] == ch["subject_ref"]), None)
        if root is None:
            continue
        accepted = REQUESTS[ch["request_type"]][1]
        for i in its:
            if (i["ev"]["sender_id"] == root["ev"]["sender_id"] and i["ev"]["created_at"] > ch["created_at"]
                    and i["interp"]["screenshot_type"] in accepted):
                done.append(respond(store, ch["challenge_id"], i["ev"]["evidence_id"]))
                break
    return done


def expire(store, trip_id, now=None):
    """The no-response path: overdue challenges become `no_response`. No Decision is created. Never a rejection."""
    now = now or cl.now_utc()
    out = []
    for ch in store.current_challenges(trip_id=trip_id):
        if ch["status"] == "issued" and vw.parse_ts(ch["due_at"]) <= now:
            nid = store.add_challenge(ch["subject_ref"], ch["trip_id"], ch["attribute"], ch["request_type"],
                                      ch["reason_code"], ch["message"], ch["due_at"], status="no_response",
                                      supersedes=ch["challenge_id"])
            out.append(_row(store, nid))
    return out
