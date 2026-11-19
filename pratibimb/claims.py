"""Claims: connected groups of one traveller's evidence (payment, bank SMS, ticket, refund ...).

A claim is a VIEW over immutable records (union of non-UNMATCHED relationships), never a stored mutable row.
Machine-observed states only. Human assertions are attached separately and labelled.
"""
import hashlib
from datetime import datetime, timezone

from . import dupes, views as vw

CLAIMABLE = ("UPI_SUCCESS", "BANK_SMS", "TICKET_QR", "REFUND_NOTICE", "CLAIM_SUBMISSION", "SUSPECT_NOTICE")
CONTEXT_ONLY = ("BOT_ERROR", "UPI_FAILED_PENDING", "OTHER")
CONTEXT_WINDOW_MIN = 30


def now_utc():
    return datetime.now(timezone.utc)


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def interp_ids_for_subject(store, ref):
    if ref.startswith("in_"):
        return [ref]
    if ref.startswith("ev_"):
        return [i["interp_id"] for i in store.interpretations_for(ref)]
    if ref.startswith("rl_"):
        r = store.get(ref)
        return [x for x in (r["from_id"], r["to_id"]) if x and x.startswith("in_")]
    if ref.startswith("dc_"):
        return interp_ids_for_subject(store, store.get(ref)["subject_ref"])
    return []


def build_claims(store, trip_id, cfg, now=None):
    now = now or now_utc()
    its = {i["id"]: i for i in vw.items(store, trip_id)}
    rels = [r for r in store.list_records("relationships")
            if r["from_id"] in its or (r["to_id"] in its)]
    parent = {i: i for i, it in its.items() if it["interp"]["screenshot_type"] in CLAIMABLE}
    dup_of, dup_flags = {}, {}
    for i, it in its.items():
        for f in dupes.detect(store, i, cfg):
            dup_flags.setdefault(i, []).append(f)
            if f["kind"] == "resend_same_sender" and i in parent and f["earlier_interp"] in parent:
                dup_of[i] = f["earlier_interp"]
    for i, e in dup_of.items():
        parent[_find(parent, i)] = _find(parent, e)
    for r in rels:
        if r["type"] != "UNMATCHED" and r["from_id"] in parent and r["to_id"] in parent:
            parent[_find(parent, r["from_id"])] = _find(parent, r["to_id"])
    groups = {}
    for i in parent:
        groups.setdefault(_find(parent, i), []).append(i)
    order = {i: n for n, i in enumerate(its)}
    claims = []
    for members in groups.values():
        members.sort(key=lambda m: order[m])
        mset = set(members)
        root = members[0]
        crels = [r for r in rels if r["from_id"] in mset or (r["to_id"] in mset)]
        claims.append({
            "claim_ref": f"claim:{root}", "root": root, "trip_id": trip_id,
            "sender_id": its[root]["ev"]["sender_id"], "interp_ids": members,
            "types": {m: its[m]["interp"]["screenshot_type"] for m in members},
            "relationships": crels,
            "duplicates": [m for m in members if m in dup_of],
            "dup_flags": [f for m in members for f in dup_flags.get(m, [])],
            "context_ids": [], "_its": its,
        })
    # attach context-only evidence (bot errors etc.) to the same traveller's nearest payment within a window
    for i, it in its.items():
        if it["interp"]["screenshot_type"] not in CONTEXT_ONLY:
            continue
        t = vw.parse_ts(it["interp"]["fields"].get("timestamp")) or vw.parse_ts(it["ev"]["received_at"])
        for c in claims:
            if c["sender_id"] != it["ev"]["sender_id"]:
                continue
            for m in c["interp_ids"]:
                if c["types"][m] in ("UPI_SUCCESS", "BANK_SMS"):
                    pt = _ts(its[m])
                    if t and pt and 0 <= (t - pt).total_seconds() <= CONTEXT_WINDOW_MIN * 60:
                        c["context_ids"].append(i)
                        break
    for c in claims:
        _derive(store, c, cfg, now)
    return claims


def _ts(it):
    return vw.parse_ts(it["interp"]["fields"].get("timestamp")) or vw.parse_ts(it["ev"]["received_at"])


def _derive(store, c, cfg, now):
    types = set(c["types"].values())
    its = c["_its"]
    pay = [m for m in c["interp_ids"] if c["types"][m] in ("UPI_SUCCESS", "BANK_SMS")]
    link_types = {r["type"] for r in c["relationships"] if r["type"] != "UNMATCHED"}
    c["rel_types"] = sorted({r["type"] for r in c["relationships"]})
    first_pay = min((_ts(its[m]) for m in pay if _ts(its[m])), default=None)
    c["age_hours"] = round((now - first_pay).total_seconds() / 3600, 2) if first_pay else None
    has_t, has_p = "TICKET_QR" in types, bool(pay)
    if "SUSPECT_NOTICE" in types:
        state, link = "suspect_notice_seen", None
    elif has_t and has_p:
        link = "MANUAL" if "MANUAL" in link_types else ("INFERRED" if "INFERRED" in link_types else "EXACT")
        state = "linked"
    elif "REFUND_NOTICE" in types and has_p:
        state, link = "refund_evidence_seen", None
    elif has_p:
        link = None
        state = "case_opened" if (c["age_hours"] or 0) >= cfg["no_ticket_hours"] else "payment_seen"
    elif has_t:
        state, link = "ticket_seen", None
    elif "REFUND_NOTICE" in types:
        state, link = "refund_seen_unmatched", None
    else:
        state, link = "claim_submitted", None
    c["state"], c["link_type"] = state, link
    # human layer, labelled
    subj = set(c["interp_ids"]) | set(c["context_ids"])
    decs = []
    for d in store.list_records("decisions"):
        if set(interp_ids_for_subject(store, d["subject_ref"])) & subj:
            decs.append(d)
    c["decisions"] = decs
    last = decs[-1] if decs else None
    c["coordinator_decision"] = None if not last else last["action"]
    c["last_action"] = None if not last else f"coordinator decision: {last['action']}"
    c["resolved"] = bool(last and last["action"] in ("approved", "rejected"))
    c["assertions"] = [a for a in store.list_assertions(c["trip_id"])
                       if a["sender_id"] == c["sender_id"] and (a["subject_ref"] in (None, *c["interp_ids"]))]
    c["traveller_asserts_travel"] = bool(c["assertions"])


def public(c):
    """Claim without the internal item cache (safe to serialise)."""
    return {k: v for k, v in c.items() if k != "_its"}
