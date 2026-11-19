"""
Reference linker + trust assessor over EXTRACTED FIELDS (stand-in for Member B's engine).

Purpose: (1) exercise the evaluation harness end to end, (2) give the dashboard flags/reasons on the
synthetic corpus. It reads only what a real pipeline would observe (type, fields, sender, time, sha256/phash/ahash),
never labels or relationships.json. Rule-based and explainable on purpose. When B's engine is live, replace its
output; nothing else changes.

Conventions (match data/relationships.json): link direction follows
  bank SMS -> payment -> ticket ; claim -> ticket ; bot error / refund -> failed payment ; duplicate -> original.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.load(open(Path(__file__).with_name("config.json")))
PAYMENTS = ("UPI_SUCCESS", "UPI_FAILED_PENDING")
CLAIMABLE = ("TICKET_QR", "UPI_SUCCESS", "BANK_SMS", "CLAIM_SUBMISSION")
RANK = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}

FLAG_REASONS = {
    "exact_file_dup": "The exact same file was sent before",
    "same_sender_resend": "Same ticket ID already sent earlier by this person (resend)",
    "earlier_sighting_other_sender": "This ticket ID was already seen from a different sender",
    "perceptual_similar": "Image looks similar to earlier evidence (similarity signal only)",
    "date_outside_window": "Date is outside the trip window",
    "suspect_notice_class": "Message looks like a refund/KYC-style notice, not an official one",
    "no_reference_on_screen": "No transaction reference visible on this screen",
    "fare_mismatch": "Claimed fare differs from the linked ticket's fare",
    "payment_no_ticket_case": "Payment seen, no ticket evidence; case opened",
    "no_payment_evidence": "Ticket references an order but no matching payment evidence was seen",
}


def _t(s):
    return datetime.fromisoformat(s) if s else None


def key(r):
    return (r["received_at"], r["evidence_id"])


def _num(v):
    try:
        return round(float(str(v).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


def observable(rec):
    """The only inputs the engine is allowed to look at."""
    f = {k: v for k, v in (rec.get("fields") or {}).items() if v is not None}
    return {"evidence_id": rec["evidence_id"], "sender_id": rec["sender_id"], "received_at": rec["received_at"],
            "trip_id": rec.get("trip_id"), "type": rec["screenshot_type"], "fields": f,
            "sha256": rec.get("sha256"), "phash": rec.get("phash"), "ahash": rec.get("ahash")}


def _hd(a, b):
    return (int(a, 16) ^ int(b, 16)).bit_count() if a and b else 99


def compute_links(recs, cfg=CFG):
    """Return [{from,to,type,basis,reason,candidates}] using shared IDs first, context second, else UNMATCHED."""
    out, by = [], {r["evidence_id"]: r for r in recs}
    win = cfg["inferred_time_window_minutes"] * 60
    P = cfg["perceptual"]

    def same_trip(a, b):
        return a.get("trip_id") == b.get("trip_id")

    for r in sorted(recs, key=key):
        f, T, eid = r["fields"], r["type"], r["evidence_id"]
        link = None
        if T == "TICKET_QR":
            earlier = [x for x in recs if x["type"] == "TICKET_QR" and key(x) < key(r) and x["evidence_id"] != eid
                       and f.get("ticket_id") and x["fields"].get("ticket_id") == f["ticket_id"]]
            if earlier:
                o = sorted(earlier, key=key)[0]
                basis = ["ticket_id"]
                if r["sha256"] and r["sha256"] == o["sha256"]:
                    basis.append("sha256")
                elif _hd(r["phash"], o["phash"]) <= P["phash_max"] and _hd(r["ahash"], o["ahash"]) <= P["ahash_max"]:
                    basis.append("perceptual_similarity")
                link = (o, "EXACT", basis, "Same ticket ID as earlier evidence; duplicate, not counted twice.")
        elif T == "BANK_SMS":
            if f.get("utr"):
                c = [x for x in recs if x["type"] in PAYMENTS and x["fields"].get("utr") == f["utr"] and same_trip(r, x)]
                if c:
                    link = (c[0], "EXACT", ["utr"], "Shares the payment's UTR.")
            if link is None:
                c = [x for x in recs if x["type"] == "UPI_SUCCESS" and same_trip(r, x) and _num(x["fields"].get("amount")) == _num(f.get("amount"))
                     and f.get("amount") and abs((_t(x["fields"]["timestamp"]) - _t(f["timestamp"])).total_seconds()) <= win]
                ids = [x["evidence_id"] for x in c]
                if len(c) == 1 and c[0]["sender_id"] == r["sender_id"]:
                    link = (c[0], "INFERRED", ["amount", "timestamp_window", "trip_context"], "Context only; no shared identifier.")
                else:
                    out.append({"from": eid, "to": c[0]["evidence_id"] if c else None, "type": "UNMATCHED", "basis": [],
                                "reason": ("Same amount and minute are insufficient; sender differs or several candidates; no shared identifier."
                                           if c else "No candidate payment found."), "candidates": ids if len(c) > 1 else None})
                    continue
        elif T == "UPI_SUCCESS":
            if f.get("order_id"):
                c = [x for x in recs if x["type"] == "TICKET_QR" and x["fields"].get("order_id") == f["order_id"] and same_trip(r, x)]
                if c:
                    link = (sorted(c, key=key)[0], "EXACT", ["order_id"], "Shares the ticket's order ID.")
            else:
                c = [x for x in recs if x["type"] == "TICKET_QR" and same_trip(r, x) and not x["fields"].get("order_id")
                     and x["sender_id"] == r["sender_id"] and _num(x["fields"].get("fare")) == _num(f.get("amount")) and f.get("amount")
                     and abs((_t(x["fields"]["timestamp"]) - _t(f["timestamp"])).total_seconds()) <= win]
                if len(c) == 1:
                    link = (c[0], "INFERRED", ["amount", "timestamp_window", "trip_context"], "Amount, time, sender and trip context agree; no shared identifier.")
                elif len(c) > 1:
                    out.append({"from": eid, "to": None, "type": "UNMATCHED", "basis": [], "reason": "Two plausible tickets; not guessed.",
                                "candidates": [x["evidence_id"] for x in c]})
                    continue
        elif T == "CLAIM_SUBMISSION" and f.get("ticket_id"):
            c = [x for x in recs if x["type"] == "TICKET_QR" and x["fields"].get("ticket_id") == f["ticket_id"]]
            if c:
                link = (sorted(c, key=key)[0], "EXACT", [k for k in ("ticket_id", "order_id") if f.get(k) and f.get(k) == sorted(c, key=key)[0]["fields"].get(k)],
                        "Repeats the ticket's references.")
        elif T in ("BOT_ERROR", "REFUND_NOTICE") and f.get("order_id"):
            c = [x for x in recs if x["type"] == "UPI_FAILED_PENDING" and x["fields"].get("order_id") == f["order_id"] and same_trip(r, x)]
            if c:
                link = (c[0], "EXACT", ["order_id"], "Shares the pending payment's order ID.")
        if link:
            o, t, basis, why = link
            out.append({"from": eid, "to": o["evidence_id"], "type": t, "basis": basis, "reason": why, "candidates": None})
    return out


def analyse(recs, trips, links=None, cfg=CFG):
    """recs: observable() dicts. trips: [{trip_id, window_start, window_end}]. links: optional authored override.
    Returns {evidence_id: assessment}."""
    links = compute_links(recs, cfg) if links is None else links
    by = {r["evidence_id"]: r for r in recs}
    trip = {t["trip_id"]: t for t in trips}
    res = {}
    # cases: failed/pending payment whose order has no ticket
    case_of = {}
    for r in recs:
        if r["type"] == "UPI_FAILED_PENDING":
            oid = r["fields"].get("order_id")
            has_ticket = oid and any(x["type"] == "TICKET_QR" and x["fields"].get("order_id") == oid for x in recs)
            if not has_ticket:
                ref = f"CASE-{oid or r['evidence_id']}"
                case_of[r["evidence_id"]] = ref
                for x in recs:
                    if x["evidence_id"] != r["evidence_id"] and oid and x["fields"].get("order_id") == oid and x["type"] in ("BOT_ERROR", "REFUND_NOTICE"):
                        case_of[x["evidence_id"]] = ref
    for r in sorted(recs, key=key):
        eid, f, T = r["evidence_id"], r["fields"], r["type"]
        flags, earlier = [], None
        out = next((l for l in links if l["from"] == eid), None)
        inc = [l for l in links if l["to"] == eid and l["type"] != "UNMATCHED"]
        prior = [x for x in recs if key(x) < key(r)]
        same_file = [x for x in prior if r["sha256"] and x["sha256"] == r["sha256"]]
        if same_file:
            flags.append("exact_file_dup")
            earlier = same_file[0]
        if T == "TICKET_QR" and f.get("ticket_id"):
            sem = sorted([x for x in prior if x["type"] == "TICKET_QR" and x["fields"].get("ticket_id") == f["ticket_id"]], key=key)
            if sem:
                earlier = earlier or sem[0]
                flags.append("same_sender_resend" if sem[0]["sender_id"] == r["sender_id"] else "earlier_sighting_other_sender")
                P = cfg["perceptual"]     # supporting signal only: needs the semantic match above AND measured closeness
                if (not same_file and _hd(r["phash"], sem[0]["phash"]) <= P["phash_max"]
                        and _hd(r["ahash"], sem[0]["ahash"]) <= P["ahash_max"]):
                    flags.append("perceptual_similar")
        tr = trip.get(r.get("trip_id"))
        ts = f.get("timestamp")
        if tr and ts and not (_t(tr["window_start"]) <= _t(ts) <= _t(tr["window_end"])):
            flags.append("date_outside_window")
        if T == "SUSPECT_NOTICE":
            flags.append("suspect_notice_class")
        if T == "BANK_SMS" and not f.get("utr"):
            flags.append("no_reference_on_screen")
        if T == "CLAIM_SUBMISSION" and out and out["to"] in by:
            tf = _num(by[out["to"]]["fields"].get("fare"))
            if tf is not None and _num(f.get("fare")) != tf:
                flags.append("fare_mismatch")
        if T == "TICKET_QR" and f.get("order_id") and not any(x["type"] in PAYMENTS and x["fields"].get("order_id") == f["order_id"] for x in recs):
            flags.append("no_payment_evidence")
        if eid in case_of:
            flags.append("payment_no_ticket_case")
        # relationship type shown on the row
        if out:
            rtype = out["type"]
        elif inc:
            rtype = sorted(inc, key=lambda l: RANK[l["type"]])[0]["type"]
        else:
            rtype = "UNMATCHED"
        via = None
        if not out and inc and rtype == "INFERRED" and not flags:
            via = sorted(inc, key=lambda l: RANK[l["type"]])[0]["from"]     # reviewed through the source item's row
        if T == "OTHER":
            ds, reasons = "insufficient", ["Not a ticket or payment screen; nothing to link"]
        else:
            reasons = [FLAG_REASONS[x] for x in flags]
            if rtype == "INFERRED":
                reasons.append("Linked by context only (no shared identifier); never auto-cleared")
            if rtype == "UNMATCHED" and not flags:
                reasons.append("No matching evidence found; kept, not forced into a link")
            if out and out["type"] == "UNMATCHED":
                reasons.append(out["reason"])
            if flags or rtype in ("INFERRED", "MANUAL") or (rtype == "UNMATCHED" and T not in ("TICKET_QR",)):
                ds = "insufficient" if (rtype == "UNMATCHED" and T == "BANK_SMS") else "needs_review"
            elif rtype == "UNMATCHED":
                ds = "needs_review"
            else:
                ds = "clear" if (rtype == "EXACT" and T in CLAIMABLE) else "needs_review"
            if ds != "clear" and not reasons:
                reasons.append("Needs a human look")
        res[eid] = {"decision_support": ds, "flags": flags, "reasons": reasons, "relationship_type": rtype,
                    "link": out, "reviewed_via": via, "case_ref": case_of.get(eid),
                    "earlier_sighting": ({"evidence_id": earlier["evidence_id"], "sender_id": earlier["sender_id"],
                                          "date": earlier["received_at"][:10]} if earlier else None),
                    "evidence_level": attr_levels(r, links, by)}
    return res


def attr_levels(r, links, by):
    """Per-attribute levels. 'independently_verified' is never produced: no authoritative source is available here."""
    eid, T = r["evidence_id"], r["type"]
    pay = None
    if T in PAYMENTS:
        pay = r
    else:
        out = next((l for l in links if l["from"] == eid and l["type"] != "UNMATCHED"), None)
        if out and by.get(out["to"], {}).get("type") in PAYMENTS:
            pay = by[out["to"]]
        elif T == "TICKET_QR":
            inc = next((l for l in links if l["to"] == eid and l["type"] in ("EXACT", "INFERRED") and by[l["from"]]["type"] in PAYMENTS), None)
            pay = by[inc["from"]] if inc else None
    debit = "none"
    if pay:
        debit = "extracted"
        if any(l["type"] == "EXACT" and l["to"] == pay["evidence_id"] and by[l["from"]]["type"] == "BANK_SMS" for l in links):
            debit = "corroborated"
    o2 = next((l for l in links if l["from"] == eid and l["type"] != "UNMATCHED"), None)
    ticket = "extracted" if (T in ("TICKET_QR", "CLAIM_SUBMISSION") or (o2 and by.get(o2["to"], {}).get("type") == "TICKET_QR")) else "none"
    return {"payment_debit": debit, "ticket_issued": ticket}
