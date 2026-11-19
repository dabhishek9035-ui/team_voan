"""B6. Trust assessment per claim: structured signals, per-attribute evidence levels, abstention.

Not a score and not a verdict. The output says what is supported, what is not, and why, in structured form
(`code` + params) so Member A can phrase it in the traveller's language. No free-text LLM reasons.

Levels are scoped to an attribute:  extracted < corroborated < independently_verified.
  corroborated = independent sources agree. It is consistency, NOT truth: two fabricated screenshots can agree.
  independently_verified = an authoritative source (producer 'authoritative:...') confirms THAT attribute.
Nothing in the pipeline produces independently_verified on its own; it needs an authoritative feed.
"""
from . import claims as cl, views as vw

LEVEL_MEANING = {
    "extracted": "Fields were read from what was submitted. Nothing else supports them yet.",
    "corroborated": "Independent submissions agree with each other. This is consistency, not proof: two fabricated screenshots can agree.",
    "independently_verified": "An authoritative source confirmed this specific attribute.",
}
SUPPORT_MEANING = {
    "clear": "No concern found and the strongest links are exact. A coordinator may still review it.",
    "needs_review": "Something is unresolved or conflicting. A coordinator decides.",
    "insufficient": "Not enough readable evidence to say anything. Asking for one more item is the next step.",
}
# code -> (direction, weight, plain_reason template)
SIGNALS = {
    "shared_identifier": ("support", 0.5, "An identifier ({fields}) is shared between the submissions."),
    "second_source_agrees": ("support", 0.3, "A second, separate submission agrees on the {attr}."),
    "earlier_sighting_same_sender": ("info", 0.1, "This item was already submitted by the same traveller (evidence {earlier})."),
    "earlier_sighting_other_sender": ("concern", 0.9, "The same item was already submitted by a different traveller on {when} (evidence {earlier})."),
    "perceptual_similarity": ("concern", 0.4, "The image looks similar to another traveller's evidence {earlier}. Similarity is only a hint."),
    "date_outside_window": ("concern", 0.7, "The travel date {when} is outside the trip window."),
    "fare_route_mismatch": ("concern", 0.5, "The ticket fare {fare} differs from the payment amount {amount}."),
    "payer_mismatch": ("concern", 0.5, "The payer name differs between linked submissions."),
    "low_extraction_confidence": ("concern", 0.4, "The reader was unsure about: {fields}."),
    "below_clear_confidence": ("concern", 0.2, "Reading confidence ({value}) is below the level needed to clear automatically."),
    "unreadable_key_field": ("concern", 0.5, "Could not read: {fields}."),
    "suspect_notice_class": ("concern", 0.9, "This message looks like a suspect notice (for example a link asking for details)."),
    "inferred_link_only": ("concern", 0.3, "The payment and ticket are matched on amount and time only; no shared identifier."),
    "ambiguous_candidates": ("concern", 0.4, "More than one earlier item fits equally well; none was chosen."),
    "no_counterpart": ("concern", 0.5, "No matching {missing} has been seen."),
    "challenge_no_response": ("info", 0.2, "An extra item was requested and has not arrived. The claim stays unverified."),
}


def _sig(code, **params):
    direction, weight, tpl = SIGNALS[code]
    return {"name": code, "code": code, "direction": direction, "weight": weight,
            "params": params, "plain_reason": tpl.format(**{k: ("n/a" if v is None else v) for k, v in params.items()})}


def _level(order, *levels):
    return max(levels, key=order.index)


ORDER = ["none", "extracted", "corroborated", "independently_verified"]


def assess(store, claim, cfg, trip=None):
    its = claim["_its"]
    ids = claim["interp_ids"]
    by_type = {}
    for m in ids:
        by_type.setdefault(claim["types"][m], []).append(its[m])
    sig = []
    fields = lambda it: it["interp"]["fields"]
    conf = lambda it: it["interp"]["field_confidence"]

    # ---- relationships
    rels = [r for r in claim["relationships"] if r["type"] != "UNMATCHED"]
    for r in rels:
        if r["type"] == "EXACT":
            sig.append(_sig("shared_identifier", fields=", ".join(r["basis"])))
        if r["type"] == "INFERRED":
            sig.append(_sig("inferred_link_only"))
    for r in claim["relationships"]:
        if r["type"] == "UNMATCHED" and any(isinstance(b, dict) for b in r["basis"]):
            sig.append(_sig("ambiguous_candidates"))

    # ---- duplicates
    for f in claim["dup_flags"]:
        if f["item_interp"] not in ids:
            continue
        if f["kind"] == "same_item_other_sender":
            sig.append(_sig("earlier_sighting_other_sender", earlier=f["earlier"], when=f["earlier_received_at"]))
        elif f["kind"] == "resend_same_sender":
            sig.append(_sig("earlier_sighting_same_sender", earlier=f["earlier"]))
        elif f["kind"] == "looks_similar_only" and not f["same_sender"]:
            sig.append(_sig("perceptual_similarity", earlier=f["earlier"]))

    # ---- per-item extraction quality
    key_confs, unreadable, low = [], [], []
    scored_ids = [m for m in ids if m not in claim["duplicates"]]
    for m in scored_ids:
        it = its[m]
        t = it["interp"]["screenshot_type"]
        for k in vw.KEY_FIELDS.get(t, ()):
            val = fields(it).get(k)
            if val is None:
                if not (t == "TICKET_QR" and k in ("ticket_id", "qr_payload") and
                        (fields(it).get("ticket_id") or fields(it).get("qr_payload"))):
                    unreadable.append(f"{k} ({t})")
            else:
                c = conf(it).get(k, 0.0)
                key_confs.append(c)
                if c < cfg["low_confidence"]:
                    low.append(f"{k} ({t})")
    if unreadable:
        sig.append(_sig("unreadable_key_field", fields=", ".join(unreadable)))
    if low:
        sig.append(_sig("low_extraction_confidence", fields=", ".join(low)))
    if "SUSPECT_NOTICE" in by_type:
        sig.append(_sig("suspect_notice_class"))
    min_conf = round(min(key_confs), 4) if key_confs else 0.0

    # ---- window, fare, payer
    window = (trip or {}).get("window_start"), (trip or {}).get("window_end")
    if window[0] and window[1]:
        lo, hi = vw.parse_ts(window[0]), vw.parse_ts(window[1])
        for t in ("TICKET_QR", "CLAIM_SUBMISSION"):
            for it in by_type.get(t, []):
                ts = vw.parse_ts(fields(it).get("timestamp"))
                if ts and not (lo <= ts <= hi):
                    sig.append(_sig("date_outside_window", when=fields(it).get("timestamp")))
    for tk in by_type.get("TICKET_QR", []):
        for p in by_type.get("UPI_SUCCESS", []):
            fa, am = fields(tk).get("fare"), fields(p).get("amount")
            if fa is not None and am is not None and _n(fa) != _n(am):
                sig.append(_sig("fare_route_mismatch", fare=fa, amount=am))
            n1, n2 = fields(tk).get("payer_name_masked"), fields(p).get("payer_name_masked")
            if n1 and n2 and n1.strip().lower() != n2.strip().lower():
                sig.append(_sig("payer_mismatch"))

    # ---- per-attribute evidence levels
    pay, sms = by_type.get("UPI_SUCCESS", []), by_type.get("BANK_SMS", [])
    tick = by_type.get("TICKET_QR", [])
    linked = lambda a, b: any(r["type"] == "EXACT" and {r["from_id"], r["to_id"]} == {a["id"], b["id"]}
                              for r in rels)
    auth = lambda its_: any(i["interp"]["producer"].startswith("authoritative:") for i in its_)
    lv = {}
    if pay or sms:
        lv["debit"] = "extracted"
        if pay and sms and (any(linked(p, s) for p in pay for s in sms)):
            lv["debit"] = "corroborated"
            sig.append(_sig("second_source_agrees", attr="debit"))
        if auth(pay + sms):
            lv["debit"] = "independently_verified"
    if tick:
        lv["ticket_issued"] = "extracted"
        if (pay or sms) and any(linked(t, p) for t in tick for p in pay + sms):
            lv["ticket_issued"] = "corroborated"
        if auth(tick):
            lv["ticket_issued"] = "independently_verified"
    if tick and pay and any(linked(t, p) and _n(fields(t).get("fare")) == _n(fields(p).get("amount"))
                            for t in tick for p in pay):
        lv["amount_consistency"] = "corroborated"
    if by_type.get("REFUND_NOTICE"):
        lv["refund_credit"] = "extracted"
        if any(r["type"] == "EXACT" for r in rels if any(
                x in [i["id"] for i in by_type["REFUND_NOTICE"]] for x in (r["from_id"], r["to_id"]))):
            lv["refund_credit"] = "corroborated"

    # ---- counterpart / case
    st = claim["state"]
    if st in ("case_opened", "payment_seen"):
        sig.append(_sig("no_counterpart", missing="ticket"))
    elif st == "ticket_seen" and not claim["duplicates"] == claim["interp_ids"]:
        sig.append(_sig("no_counterpart", missing="payment"))
    elif st == "refund_seen_unmatched":
        sig.append(_sig("no_counterpart", missing="payment"))
    # ---- challenges
    chal = store.current_challenges(subject_ref=claim["root"])
    if any(c["status"] == "no_response" for c in chal):
        sig.append(_sig("challenge_no_response"))

    seen, uniq = set(), []
    for s in sig:
        k = (s["code"], tuple(sorted(s["params"].items())))
        if k not in seen:
            seen.add(k); uniq.append(s)
    sig[:] = uniq
    concerns = [s for s in sig if s["direction"] == "concern"]
    # decision support
    if st == "suspect_notice_seen":
        support = "needs_review"
    elif unreadable or (st in ("payment_seen", "ticket_seen", "refund_seen_unmatched", "claim_submitted")
                        and not rels and not any(s["code"] == "ambiguous_candidates" for s in sig)
                        and not claim["dup_flags"]):
        support = "insufficient"
    elif concerns:
        support = "needs_review"
    elif claim["link_type"] == "EXACT" and lv.get("ticket_issued") == "corroborated" \
            and lv.get("amount_consistency") == "corroborated" and cfg["link_mode"] == "exact+inferred":
        if min_conf >= cfg["clear_min_conf"]:
            support = "clear"
        else:
            sig.append(_sig("below_clear_confidence", value=min_conf))
            support = "needs_review"
    else:
        support = "needs_review"
        if not concerns:
            sig.append(_sig("inferred_link_only") if claim["link_type"] in ("INFERRED", "MANUAL") or not rels
                       else _sig("below_clear_confidence", value=min_conf))
    # a manual link is a human judgment: still reviewable evidence, not machine 'clear'
    if claim["link_type"] == "MANUAL" and support == "clear":
        support = "needs_review"
    reasons = [s for s in sig if s["direction"] in ("concern", "info")]
    assert support == "clear" or reasons or support == "insufficient", "every non-clear outcome needs a reason"
    if support == "insufficient" and not reasons:
        reasons = [_sig("unreadable_key_field", fields="a key field") if unreadable else _sig("no_counterpart", missing="second source")]
        sig.extend(reasons)
    return {
        "claim_ref": claim["claim_ref"], "state": st,
        "evidence_level": lv, "level_meaning": {l: LEVEL_MEANING[l] for l in set(lv.values())},
        "relationship_type": (claim["link_type"] or (claim["rel_types"][0] if claim["rel_types"] else "UNMATCHED")),
        "relationship_types": claim["rel_types"] or ["UNMATCHED"],
        "signals": sig, "decision_support": support, "decision_support_meaning": SUPPORT_MEANING[support],
        "min_key_confidence": min_conf,
        "label": ("unverified: needs review" if support != "clear" else "no concern found; consistent submissions"),
    }


def _n(x):
    try:
        return round(float(str(x).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None
