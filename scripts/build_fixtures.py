#!/usr/bin/env python3
"""Generate fixtures/scenarios.json deterministically.

ALL DATA IS SYNTHETIC. Names, UTRs, ticket ids and QR payloads are invented; the layouts are
guesses until Member A's Day-0 report replaces them with real (masked) shapes.
Hashes are derived from labels so duplicates share them exactly and "cropped" copies differ
by a known number of bits (so Day-3 perceptual thresholds can be tested against ground truth).
"""
import hashlib
import json
import os
import sys

ALL_FIELDS = ["amount", "currency", "timestamp", "utr", "order_id", "ticket_id", "qr_payload",
              "origin_station", "destination_station", "fare", "payer_name_masked", "payee_name",
              "status_text", "app_name", "bank_name", "language_detected"]


def sha(label):
    return hashlib.sha256(f"pratibimb-fixture:{label}".encode()).hexdigest()


def ph(label):
    return hashlib.sha256(f"phash:{label}".encode()).hexdigest()[:16]


def flip_bits(hexstr, n):
    """Return hexstr with exactly n distinct bits flipped (Hamming distance n)."""
    val = int(hexstr, 16)
    for bit in range(n):
        val ^= 1 << (bit * 7 % 64)
    return f"{val:016x}"


def hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def interp(stype, tconf, f, lang="en", conf=0.95, src=None, job=None):
    fields = {k: f.get(k) for k in ALL_FIELDS}
    fields["language_detected"] = fields["language_detected"] or lang
    confs, sources = {}, {}
    for k in ALL_FIELDS:
        if fields[k] is None:
            confs[k], sources[k] = 0.0, None
        else:
            confs[k] = (conf.get(k, 0.95) if isinstance(conf, dict) else conf)
            sources[k] = (src or {}).get(k, "qr_decoder" if k == "qr_payload" else "sarvam_extract")
    return {"producer": "fixture:hand-written", "model_version": "fixtures-v1", "sarvam_job_id": job,
            "screenshot_type": stype, "type_confidence": tconf, "fields": fields,
            "field_confidence": confs, "field_source": sources, "language_detected": lang}


def item(key, sender, channel, ts, sha_label, phash, interpretation, ahash=None):
    return {"key": key, "sender_id": sender, "channel": channel, "received_at": ts,
            "sha256": sha(sha_label), "phash": phash, "ahash": ahash or ph("a-" + sha_label),
            "interpretation": interpretation}


def rel(frm, to, typ, basis, score, reason, by="system:linker"):
    return {"from": frm, "to": to, "type": typ, "basis": basis, "score": score, "reason": reason, "created_by": by}


T = "+05:30"
scenarios = []

# 1 ---------------------------------------------------------------- clean linked journey
scenarios.append({
    "name": "clean_linked_journey",
    "description": "UPI success, bank SMS and metro ticket share UTR / order id. All links EXACT.",
    "items": [
        item("pay", "s_asha", "telegram", f"2026-11-18T08:41:30{T}", "asha-pay", ph("asha-pay"),
             interp("UPI_SUCCESS", 0.98, {"amount": "40.00", "currency": "INR", "timestamp": f"2026-11-18T08:41:12{T}",
                    "utr": "631912345678", "order_id": "NMB-ORD-90417", "payee_name": "BMRCL Namma Metro",
                    "payer_name_masked": "A**a K.", "status_text": "Payment successful", "app_name": "PhonePe"})),
        item("sms", "s_asha", "telegram", f"2026-11-18T08:43:05{T}", "asha-sms", ph("asha-sms"),
             interp("BANK_SMS", 0.97, {"amount": "40.00", "currency": "INR", "timestamp": f"2026-11-18T08:41:50{T}",
                    "utr": "631912345678", "bank_name": "HDFC Bank", "status_text": "debited"})),
        item("tkt", "s_asha", "telegram", f"2026-11-18T08:42:10{T}", "asha-tkt", ph("asha-tkt"),
             interp("TICKET_QR", 0.99, {"amount": "40.00", "currency": "INR", "timestamp": f"2026-11-18T08:41:40{T}",
                    "order_id": "NMB-ORD-90417", "ticket_id": "NMB26111800417",
                    "qr_payload": "NMB|26111800417|MAJ|MGR|40.00", "origin_station": "Majestic",
                    "destination_station": "MG Road", "fare": "40.00", "app_name": "Namma Metro WhatsApp bot"})),
    ],
    "relationships": [
        rel("pay", "sms", "EXACT", ["utr"], 0.99, "Same UTR 631912345678 on payment screen and bank SMS."),
        rel("pay", "tkt", "EXACT", ["order_id"], 0.98, "Same order id NMB-ORD-90417 on payment screen and ticket."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["EXACT", "EXACT"], "case_expected": False, "dup_flags": []},
})

# 2 ---------------------------------------------------------------- payment with no ticket (Kannada bot error)
scenarios.append({
    "name": "payment_no_ticket",
    "description": "Money left the account, the bot reported failure (in Kannada), no ticket ever arrived.",
    "items": [
        item("pay", "s_ravi", "telegram", f"2026-11-18T09:10:40{T}", "ravi-pay", ph("ravi-pay"),
             interp("UPI_SUCCESS", 0.97, {"amount": "30.00", "currency": "INR", "timestamp": f"2026-11-18T09:10:22{T}",
                    "utr": "631912349901", "payee_name": "BMRCL Namma Metro", "payer_name_masked": "R**i S.",
                    "status_text": "Payment successful", "app_name": "Google Pay"})),
        item("err", "s_ravi", "telegram", f"2026-11-18T09:12:00{T}", "ravi-err", ph("ravi-err"),
             interp("BOT_ERROR", 0.9, {"status_text": "ಬುಕಿಂಗ್ ವಿಫಲವಾಗಿದೆ", "timestamp": f"2026-11-18T09:10:50{T}",
                    "app_name": "Namma Metro WhatsApp bot", "language_detected": "kn"}, lang="kn", conf=0.82)),
    ],
    "relationships": [
        rel("pay", None, "UNMATCHED", [], None, "Payment seen; no ticket evidence with a shared identifier or matching amount/time."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["UNMATCHED"], "case_expected": True, "dup_flags": []},
})

# 3 ---------------------------------------------------------------- exact duplicate, same sender
tk3 = {"amount": "50.00", "currency": "INR", "timestamp": f"2026-11-18T18:02:10{T}", "order_id": "NMB-ORD-90555",
       "ticket_id": "NMB26111800555", "qr_payload": "NMB|26111800555|IND|MAJ|50.00", "origin_station": "Indiranagar",
       "destination_station": "Majestic", "fare": "50.00", "app_name": "Namma Metro app"}
p_meera = ph("meera-tkt")
scenarios.append({
    "name": "exact_duplicate_same_sender",
    "description": "Same file sent twice by the same traveller: identical sha256, phash and ticket id.",
    "items": [
        item("first", "s_meera", "whatsapp", f"2026-11-18T18:03:00{T}", "meera-tkt", p_meera, interp("TICKET_QR", 0.99, tk3)),
        item("resend", "s_meera", "whatsapp", f"2026-11-18T18:09:00{T}", "meera-tkt", p_meera, interp("TICKET_QR", 0.99, tk3)),
    ],
    "relationships": [],
    "decisions": [],
    "expect": {"relationship_types": [], "case_expected": False,
               "dup_flags": [{"item": "resend", "earlier": "first", "layers": ["semantic", "exact_file", "perceptual"], "same_sender": True}]},
})

# 4 ---------------------------------------------------------------- cropped duplicate
p_crop = flip_bits(p_meera, 4)
crop_fields = dict(tk3)
crop_fields["ticket_id"] = None          # the crop cut off the ticket id text; the QR still decodes
crop_conf = {"qr_payload": 0.97, "amount": 0.9, "timestamp": 0.9, "order_id": 0.9, "currency": 0.9,
             "origin_station": 0.9, "destination_station": 0.9, "fare": 0.9, "app_name": 0.9}
scenarios.append({
    "name": "cropped_duplicate",
    "description": "Same ticket, cropped and recompressed: different sha256, phash 4 bits away, ticket id cut off, QR intact.",
    "items": [
        item("first", "s_meera", "whatsapp", f"2026-11-18T18:03:00{T}", "meera-tkt", p_meera, interp("TICKET_QR", 0.99, tk3)),
        item("cropped", "s_meera", "whatsapp", f"2026-11-18T18:20:00{T}", "meera-tkt-cropped", p_crop,
             interp("TICKET_QR", 0.93, crop_fields, conf=crop_conf)),
    ],
    "relationships": [],
    "decisions": [],
    "expect": {"relationship_types": [], "case_expected": False,
               "phash_distance": hamming(p_meera, p_crop),
               "dup_flags": [{"item": "cropped", "earlier": "first", "layers": ["semantic", "perceptual"], "same_sender": True}]},
})

# 5 ---------------------------------------------------------------- cross-sender duplicate
scenarios.append({
    "name": "cross_sender_duplicate",
    "description": "A different traveller submits Meera's exact ticket as their own claim. Must be distinguishable from a resend.",
    "items": [
        item("original", "s_meera", "whatsapp", f"2026-11-18T18:03:00{T}", "meera-tkt", p_meera, interp("TICKET_QR", 0.99, tk3)),
        item("other_sender", "s_kiran", "telegram", f"2026-11-19T09:30:00{T}", "meera-tkt", p_meera, interp("CLAIM_SUBMISSION", 0.9, tk3)),
    ],
    "relationships": [],
    "decisions": [],
    "expect": {"relationship_types": [], "case_expected": False,
               "dup_flags": [{"item": "other_sender", "earlier": "original", "layers": ["semantic", "exact_file", "perceptual"], "same_sender": False}]},
})

# 6 ---------------------------------------------------------------- out-of-window ride
scenarios.append({
    "name": "out_of_window_ride",
    "description": "Claim for the 18 Nov trip, but the ticket is dated 2 Oct 2026.",
    "items": [
        item("claim", "s_divya", "telegram", f"2026-11-19T10:00:00{T}", "divya-claim", ph("divya-claim"),
             interp("CLAIM_SUBMISSION", 0.92, {"amount": "35.00", "currency": "INR", "timestamp": f"2026-10-02T08:15:00{T}",
                    "ticket_id": "NMB26100200133", "qr_payload": "NMB|26100200133|TRI|MAJ|35.00", "origin_station": "Trinity",
                    "destination_station": "Majestic", "fare": "35.00", "payer_name_masked": "D**a P.", "app_name": "Namma Metro app"})),
    ],
    "relationships": [
        rel("claim", None, "UNMATCHED", [], None, "Ticket dated 2026-10-02 is outside the trip window; no payment evidence for it."),
    ],
    "decisions": [{"subject": "claim", "action": "proof_requested", "decided_by": "coordinator:c_priya",
                   "reason": "Ticket date is outside the trip window. Asked traveller for bank SMS."}],
    "expect": {"relationship_types": ["UNMATCHED"], "case_expected": False, "dup_flags": [], "signals": ["date_outside_window"]},
})

# 7 ---------------------------------------------------------------- inferred-only link
scenarios.append({
    "name": "inferred_only_link",
    "description": "Payment and ticket share no identifier. Amount, time (2 min) and payer agree, so INFERRED, never auto-cleared.",
    "items": [
        item("pay", "s_noor", "telegram", f"2026-11-18T07:55:30{T}", "noor-pay", ph("noor-pay"),
             interp("UPI_SUCCESS", 0.96, {"amount": "25.00", "currency": "INR", "timestamp": f"2026-11-18T07:55:10{T}",
                    "utr": "631912340022", "payee_name": "BMRCL Namma Metro", "payer_name_masked": "N**r A.", "app_name": "Paytm"})),
        item("tkt", "s_noor", "telegram", f"2026-11-18T07:57:20{T}", "noor-tkt", ph("noor-tkt"),
             interp("TICKET_QR", 0.97, {"amount": "25.00", "currency": "INR", "timestamp": f"2026-11-18T07:57:02{T}",
                    "ticket_id": "NMB26111800210", "qr_payload": "NMB|26111800210|BYP|IND|25.00", "origin_station": "Baiyappanahalli",
                    "destination_station": "Indiranagar", "fare": "25.00", "payer_name_masked": "N**r A.", "app_name": "Namma Metro app"})),
    ],
    "relationships": [
        rel("pay", "tkt", "INFERRED", ["amount", "timestamp_window", "payer_name_masked"], 0.7,
            "Amount 25.00 equal; ticket 112 seconds after payment; payer matches. No shared identifier."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["INFERRED"], "case_expected": False, "dup_flags": []},
})

# 8 ---------------------------------------------------------------- unmatched refund
scenarios.append({
    "name": "unmatched_refund",
    "description": "Refund credit with a reference that matches no payment seen on this trip.",
    "items": [
        item("refund", "s_ravi", "telegram", f"2026-11-24T11:00:00{T}", "ravi-refund", ph("ravi-refund"),
             interp("REFUND_NOTICE", 0.94, {"amount": "30.00", "currency": "INR", "timestamp": f"2026-11-24T10:41:00{T}",
                    "utr": "631912999999", "bank_name": "ICICI Bank", "status_text": "credited: refund"})),
    ],
    "relationships": [
        rel("refund", None, "UNMATCHED", [], None, "Refund reference 631912999999 matches no payment UTR; amount-only match would be ambiguous."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["UNMATCHED"], "case_expected": False, "dup_flags": []},
})

# 9 ---------------------------------------------------------------- ambiguous two candidates
scenarios.append({
    "name": "ambiguous_two_candidates",
    "description": "Two 25.00 payments minutes apart and one 25.00 refund with no reference: UNMATCHED listing both candidates, no coin flip.",
    "items": [
        item("payA", "s_kiran", "telegram", f"2026-11-18T08:00:00{T}", "kiran-payA", ph("kiran-payA"),
             interp("UPI_SUCCESS", 0.96, {"amount": "25.00", "currency": "INR", "timestamp": f"2026-11-18T07:59:40{T}",
                    "utr": "631912340101", "payer_name_masked": "K**n R.", "app_name": "PhonePe"})),
        item("payB", "s_kiran", "telegram", f"2026-11-18T08:03:00{T}", "kiran-payB", ph("kiran-payB"),
             interp("UPI_SUCCESS", 0.96, {"amount": "25.00", "currency": "INR", "timestamp": f"2026-11-18T08:02:40{T}",
                    "utr": "631912340102", "payer_name_masked": "K**n R.", "app_name": "PhonePe"})),
        item("refund", "s_kiran", "telegram", f"2026-11-26T12:00:00{T}", "kiran-refund", ph("kiran-refund"),
             interp("REFUND_NOTICE", 0.9, {"amount": "25.00", "currency": "INR", "timestamp": f"2026-11-26T11:50:00{T}",
                    "bank_name": "SBI", "status_text": "credited: refund"})),
    ],
    "relationships": [
        rel("refund", None, "UNMATCHED", [{"candidate": "payA"}, {"candidate": "payB"}], None,
            "Two payments of 25.00 are equally plausible; no reference on the refund. Candidates listed for the coordinator."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["UNMATCHED"], "case_expected": False, "dup_flags": [], "candidates": 2},
})

# 10 --------------------------------------------------------------- suspect notice
scenarios.append({
    "name": "suspect_notice",
    "description": "A refund-looking message asking to click a link and update KYC. Classed SUSPECT_NOTICE, never linked.",
    "items": [
        item("scam", "s_ravi", "telegram", f"2026-11-25T14:00:00{T}", "ravi-scam", ph("ravi-scam"),
             interp("SUSPECT_NOTICE", 0.88, {"amount": "30.00", "currency": "INR",
                    "status_text": "Your metro refund of Rs 30 is pending. Update KYC at the link within 2 hours.",
                    "app_name": "SMS"}, conf=0.85)),
    ],
    "relationships": [
        rel("scam", None, "UNMATCHED", [], None, "Classified as a suspect notice; not related to any payment."),
    ],
    "decisions": [],
    "expect": {"relationship_types": ["UNMATCHED"], "case_expected": False, "dup_flags": [], "signals": ["suspect_notice_class"]},
})

# 11 --------------------------------------------------------------- manual link by coordinator
scenarios.append({
    "name": "manual_link",
    "description": "No shared id and amounts differ (fare changed). Coordinator links them explicitly: MANUAL + manual_link decision.",
    "items": [
        item("pay", "s_arjun", "whatsapp", f"2026-11-18T19:30:00{T}", "arjun-pay", ph("arjun-pay"),
             interp("UPI_SUCCESS", 0.95, {"amount": "60.00", "currency": "INR", "timestamp": f"2026-11-18T19:29:40{T}",
                    "utr": "631912340777", "payer_name_masked": "A**n M.", "app_name": "BHIM"})),
        item("tkt", "s_arjun", "whatsapp", f"2026-11-18T19:41:00{T}", "arjun-tkt", ph("arjun-tkt"),
             interp("TICKET_QR", 0.95, {"amount": "55.00", "currency": "INR", "timestamp": f"2026-11-18T19:40:10{T}",
                    "ticket_id": "NMB26111800777", "qr_payload": "NMB|26111800777|WHT|MAJ|55.00", "origin_station": "Whitefield (Kadugodi)",
                    "destination_station": "Majestic", "fare": "55.00", "app_name": "Namma Metro app"})),
    ],
    "relationships": [
        rel("pay", "tkt", "MANUAL", ["coordinator_judgement"], None,
            "Coordinator linked the payment to the ticket after speaking to the traveller (Rs 5 difference explained).",
            by="coordinator:c_priya"),
    ],
    "decisions": [{"subject": "tkt", "action": "manual_link", "decided_by": "coordinator:c_priya",
                   "reason": "Linked payment to ticket after speaking to the traveller."}],
    "expect": {"relationship_types": ["MANUAL"], "case_expected": False, "dup_flags": []},
})

fixture = {
    "fixture_version": "1", "synthetic": True,
    "note": "Hand-made and synthetic. Replace with masked real shapes from Member A's Day-0 report.",
    "trip": {"trip_id": "trip_demo", "name": "Bengaluru offsite commute reimbursement, Nov 2026", "coordinator_id": "c_priya",
             "window_start": "2026-11-18T00:00:00+05:30", "window_end": "2026-11-19T23:59:59+05:30"},
    "travellers": [{"sender_id": s, "label": s} for s in
                   ["s_asha", "s_ravi", "s_meera", "s_kiran", "s_divya", "s_noor", "s_arjun"]],
    "scenarios": scenarios,
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "fixtures", "scenarios.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.normpath(out)}: {len(scenarios)} scenarios, "
          f"{sum(len(s['items']) for s in scenarios)} evidence items")
