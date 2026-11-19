"""B4. Linking engine: EXACT, INFERRED, MANUAL, UNMATCHED, each with basis[], score and a plain reason.

Candidates are the SAME traveller's other evidence on the SAME trip. An identifier shared with a different
traveller is a duplicate signal (see dupes.py), never a link.

EXACT      shared utr / order_id / ticket_id / qr_payload          eligible for auto-clear
INFERRED   amount + time window (+ payer, fare context) agree      never auto-clears
MANUAL     coordinator link (a Relationship paired with a 'manual_link' Decision)
UNMATCHED  nothing sufficient, or ambiguous (candidates listed, no coin flip)

link_mode "inferred_only" (Day-0 gate: no shared identifiers in the real world) disables EXACT; every link is
INFERRED and goes to a human. Both paths are built; config chooses.
"""
from . import views as vw

PAYMENTS = ("UPI_SUCCESS", "BANK_SMS")
TICKETS = ("TICKET_QR",)
LOOKBACK = ("UPI_SUCCESS", "BANK_SMS", "TICKET_QR")   # what a refund/claim may point back to
NEVER_LINK = ("SUSPECT_NOTICE", "BOT_ERROR", "UPI_FAILED_PENDING", "OTHER")
TERMINAL = ("REFUND_NOTICE", "CLAIM_SUBMISSION", "SUSPECT_NOTICE")  # UNMATCHED immediately if nothing found


def _num(x):
    try:
        return round(float(str(x).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


def _payer_state(a, b):
    pa, pb = a["interp"]["fields"].get("payer_name_masked"), b["interp"]["fields"].get("payer_name_masked")
    if not pa or not pb:
        return None
    return pa.strip().lower() == pb.strip().lower()


def _existing(store, a_id, b_id):
    for r in store.list_records("relationships"):
        if {r["from_id"], r["to_id"]} == {a_id, b_id}:
            return r
    return None


def _exact_candidates(me, pool):
    mine = vw.ids_of(me)
    out = []
    for o in pool:
        shared = sorted(k for k, val in mine.items() if val and val == vw.ids_of(o)[k])
        if shared:
            out.append((o, shared))
    return out


def _inferred_score(me, o, cfg):
    """Return (score, basis, reason) or None if the pair is not a plausible inferred match."""
    mf, of = me["interp"]["fields"], o["interp"]["fields"]
    types = {me["interp"]["screenshot_type"], o["interp"]["screenshot_type"]}
    amt_me = _num(mf.get("amount") if mf.get("amount") is not None else mf.get("fare"))
    amt_o = _num(of.get("amount") if of.get("amount") is not None else of.get("fare"))
    if amt_me is None or amt_o is None or amt_me != amt_o:
        return None
    # An explicit, different UTR on both sides means they are different transactions.
    u1, u2 = vw.norm_id(mf.get("utr")), vw.norm_id(of.get("utr"))
    if u1 and u2 and u1 != u2:
        return None
    t1, t2 = vw.parse_ts(mf.get("timestamp")), vw.parse_ts(of.get("timestamp"))
    if not t1 or not t2:
        return None
    gap_min = abs((t1 - t2).total_seconds()) / 60.0
    basis, score = ["amount"], 0.4
    if "REFUND_NOTICE" in types:
        refund_t, pay_t = (t1, t2) if me["interp"]["screenshot_type"] == "REFUND_NOTICE" else (t2, t1)
        if not 0 <= (refund_t - pay_t).total_seconds() <= cfg["refund_window_days"] * 86400:
            return None
        basis.append("refund_after_payment")
        score += 0.3
    else:
        if gap_min > cfg["inferred_window_minutes"]:
            return None
        basis.append("timestamp_window")
        score += 0.3 * (1 - gap_min / (cfg["inferred_window_minutes"] + 1e-9))
    payer = _payer_state(me, o)
    if payer is False:
        return None
    if payer:
        basis.append("payer_name_masked")
        score += 0.2
    if {"TICKET_QR", "UPI_SUCCESS"} <= types or {"TICKET_QR", "BANK_SMS"} <= types:
        if _num(mf.get("fare")) == _num(of.get("amount")) or _num(of.get("fare")) == _num(mf.get("amount")):
            basis.append("fare_equals_amount")
            score += 0.1
    score = round(min(score, 0.95), 2)   # inferred never reaches certainty
    if score < cfg["inferred_min_score"]:
        return None
    return score, basis, f"Amount, time and context agree ({', '.join(basis)}) but no shared identifier."


def _pool(me, all_items, trip_id):
    kinds = LOOKBACK
    out = []
    for o in all_items:
        if o["id"] == me["id"] or o["ev"]["sender_id"] != me["ev"]["sender_id"]:
            continue
        if o["ev"]["trip_id"] != trip_id or o["interp"]["screenshot_type"] not in kinds:
            continue
        if o["interp"]["screenshot_type"] == me["interp"]["screenshot_type"]:
            continue     # same type = resend/duplicate, not a link
        out.append(o)
    return out


def link_interpretation(store, interp_id, cfg):
    """Create relationships for one interpretation. Returns the list of Relationship records created."""
    all_items = vw.items(store)
    me = next((i for i in all_items if i["id"] == interp_id), None)
    if me is None:
        return []
    stype = me["interp"]["screenshot_type"]
    by = "system:linker-v1"
    created = []

    def add(to, rtype, basis, score, reason):
        if to is not None and _existing(store, interp_id, to):
            return
        rid = store.add_relationship(interp_id, to, rtype, basis, score, reason, by)
        created.append(store.get(rid))

    if stype in NEVER_LINK:
        if stype == "SUSPECT_NOTICE":
            add(None, "UNMATCHED", [], None, "Classified as a suspect notice; it is never linked to a payment or ticket.")
        return created
    pool = _pool(me, all_items, me["ev"]["trip_id"])
    # Payments link to tickets and vice versa; refunds and claims look back at payments/tickets.
    if stype in PAYMENTS:
        pool = [o for o in pool if o["interp"]["screenshot_type"] in TICKETS + PAYMENTS]
    elif stype in TICKETS:
        pool = [o for o in pool if o["interp"]["screenshot_type"] in PAYMENTS]
    elif stype == "REFUND_NOTICE":
        pool = [o for o in pool if o["interp"]["screenshot_type"] in PAYMENTS]
    if stype in PAYMENTS:   # an earlier ticket pointing forward at a later payment is covered when the ticket arrives
        pool = [o for o in pool if o["interp"]["screenshot_type"] != stype]

    if cfg["link_mode"] == "exact+inferred":
        ex = _exact_candidates(me, pool)
        if ex:
            for o, shared in ex:
                add(o["id"], "EXACT", shared, 0.99 if "utr" in shared or "ticket_id" in shared else 0.98,
                    f"Shared identifier: {', '.join(shared)}.")
            return created
    # Inferred path (and the whole path in inferred_only mode, where shared identifiers also count as INFERRED).
    scored = []
    for o in pool:
        s = _inferred_score(me, o, cfg)
        if s is None and cfg["link_mode"] == "inferred_only":
            ex = _exact_candidates(me, [o])
            if ex:
                s = (0.9, [f"shared:{k}" for k in ex[0][1]], "Identifier agrees; inferred_only mode requires human review.")
        if s:
            scored.append((o, *s))
    if len(scored) == 1:
        o, score, basis, reason = scored[0]
        add(o["id"], "INFERRED", basis, score, reason)
    elif len(scored) > 1:
        add(None, "UNMATCHED", [{"candidate": o["id"]} for o, *_ in scored], None,
            f"{len(scored)} candidates fit equally well; not forcing a choice. A coordinator must pick.")
    elif stype in TERMINAL:
        from .dupes import detect
        if any(f["strength"] in ("identifier", "file") and not f["same_sender"] for f in detect(store, interp_id, cfg)):
            return created     # a duplicate of someone else's item: the duplicate flag carries the reason
        add(None, "UNMATCHED", [], None, "No payment or ticket on this trip fits this item.")
    return created


def link_manual(store, from_id, to_id, coordinator, reason, snapshot_hash):
    """Coordinator explicit link: MANUAL relationship + manual_link Decision. Supersedes a current UNMATCHED."""
    coordinator = coordinator if coordinator.startswith("coordinator:") else f"coordinator:{coordinator}"
    supersedes = None
    for r in store.list_records("relationships"):
        if r["type"] == "UNMATCHED" and r["from_id"] in (from_id, to_id):
            supersedes = r["rel_id"]
            break
    rid = store.add_relationship(from_id, to_id, "MANUAL", ["coordinator_judgement"], None, reason,
                                 coordinator, supersedes=supersedes)
    did = store.add_decision(to_id, "manual_link", coordinator, reason, snapshot_hash)
    return rid, did
