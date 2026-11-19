#!/usr/bin/env python3
"""
Pratibimb - Member B fixture generator (B1/B9).

Produces deterministic, hash-chained fixture data in the shared contract shape
(Evidence / Interpretation / Relationship / Decision + trips, travellers, cases).

  python generate_fixtures.py                 # writes both modes
  python generate_fixtures.py --mode exact    # shared ids exist (Day-0 "exact" path)
  python generate_fixtures.py --verify fixtures_exact.json

Two modes because the Day-0 gate decides which linking path is on:
  exact          order_id is on BOTH the UPI screen and the ticket  -> EXACT links
  inferred_only  no shared identifier                                -> INFERRED only

ASSUMPTIONS (all synthetic, none measured):
  - order_id as a shared identifier is a GUESS until Day-0 confirms it.
  - QR payloads are opaque random strings (used as dup keys only, never validity).
  - file_ref / hashes are placeholders; no real images exist. phash distances
    for the cropped duplicate are hand-set (Hamming 4), not measured.
"""
import argparse, hashlib, json, random, sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DAY = datetime(2026, 11, 21, tzinfo=IST)                 # trip day
WINDOW = (DAY.replace(hour=6), (DAY + timedelta(days=1)).replace(hour=23))
STATIONS = ["Baiyappanahalli", "Indiranagar", "Halasuruvu", "Trinity", "MG Road",
            "Cubbon Park", "Vidhana Soudha", "Majestic"]
APPS, BANKS = ["GPay", "PhonePe", "Paytm"], ["HDFC", "SBI", "ICICI", "Axis"]

# 10 travellers; masked names only (fields are masked at the API layer anyway)
TRAVELLERS = [("Meera K.", "Me**a K."), ("Arjun S.", "Ar**n S."), ("Kavya R.", "Ka**a R."),
              ("Rohan M.", "Ro**n M."), ("Divya P.", "Di**a P."), ("Sameer A.", "Sa**r A."),
              ("Pooja N.", "Po**a N."), ("Imran Q.", "Im**n Q."), ("Neha V.", "Ne**a V."),
              ("Vikram D.", "Vi**m D.")]


def canon(o):  # canonical JSON for hashing
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def H(s):
    return hashlib.sha256(s.encode()).hexdigest()


def chain(records):
    """Global chain: record_hash = H(canon(record) + prev_hash). Tamper-EVIDENT only."""
    prev = "GENESIS"
    for r in records:
        r.pop("prev_hash", None); r.pop("record_hash", None)
        r["prev_hash"] = prev
        r["record_hash"] = H(canon(r) + prev)   # r includes prev_hash, excludes record_hash
        prev = r["record_hash"]
    return records


def verify(ledger):
    prev = "GENESIS"
    for i, r in enumerate(ledger):
        body = {k: v for k, v in r.items() if k != "record_hash"}
        if r["prev_hash"] != prev or H(canon(body) + prev) != r["record_hash"]:
            return False, i, r.get("kind"), r.get(next((k for k in r if k.endswith("_id")), ""), "?")
        prev = r["record_hash"]
    return True, None, None, None


def build(mode, seed=7):
    rnd = random.Random(seed)
    exact = mode == "exact"
    ev, it, rel, dec, cases, gt = [], [], [], [], [], {}
    n = {"ev": 0, "in": 0, "rl": 0, "dc": 0, "cs": 0}

    def nid(p):
        n[p] += 1
        return f"{p}_{n[p]:03d}"

    def iso(d): return d.isoformat()

    def hexs(bits): return f"{rnd.getrandbits(bits):0{bits // 4}x}"

    def add(sender, stype, at, fields, scenario, lang="en", conf=0.95, low=(), phash=None,
            sha=None, tconf=0.96):
        """Create Evidence + Interpretation. `low` = fields given low confidence."""
        e_id, i_id = nid("ev"), nid("in")
        recv = at + timedelta(seconds=rnd.randint(5, 25))
        base = {k: None for k in ["amount", "currency", "timestamp", "utr", "order_id", "ticket_id",
                                  "qr_payload", "origin_station", "destination_station", "fare",
                                  "payer_name_masked", "payee_name", "status_text", "app_name",
                                  "bank_name", "language_detected"]}
        base.update(fields); base["language_detected"] = lang
        if "amount" in fields or "fare" in fields: base["currency"] = "INR"
        base["timestamp"] = iso(at)
        fc = {k: round(min(0.99, max(0.05, rnd.gauss(conf, 0.02))), 2)
              for k, v in base.items() if v is not None and k not in ("currency", "language_detected")}
        for k in low:
            if k in fc: fc[k] = round(rnd.uniform(0.3, 0.55), 2)
        ev.append({"kind": "evidence", "evidence_id": e_id, "trip_id": "trip_001", "sender_id": sender,
                   "channel": "telegram", "received_at": iso(recv), "file_ref": f"fixtures/img/{e_id}.png",
                   "sha256": sha or H(f"{seed}:{e_id}:{scenario}"), "phash": phash or hexs(64),
                   "ahash": hexs(64), "status": "interpreted", "created_at": iso(recv)})
        it.append({"kind": "interpretation", "interp_id": i_id, "evidence_id": e_id,
                   "producer": "fixture_seed", "model_version": "fixture-v1", "sarvam_job_id": None,
                   "screenshot_type": stype, "type_confidence": round(tconf, 2), "fields": base,
                   "field_confidence": fc, "raw_text_ref": None, "language_detected": lang,
                   "created_at": iso(recv + timedelta(seconds=8)), "supersedes": None})
        gt[e_id] = {"scenario": scenario, "interp_id": i_id, "expected_type": stype, "sender_id": sender}
        return e_id

    def link(a, b, typ, basis, score, why, **kw):
        r = nid("rl")
        rel.append({"kind": "relationship", "rel_id": r, "from_id": a, "to_id": b, "type": typ,
                    "basis": basis, "score": score, "reason": why, "created_by": "fixture_seed",
                    "created_at": iso(max(datetime.fromisoformat(e["received_at"]) for e in ev
                                      if e["evidence_id"] in (a, b)) + timedelta(seconds=12)),
                    "supersedes": kw.get("supersedes"),
                    "candidates": kw.get("candidates")})
        return r

    sid = lambda i: f"tg_{1001 + i}"
    t0 = DAY.replace(hour=9, minute=15)

    def pay(i, at, amt, oid, utr=None, bank=None):
        f = dict(amount=amt, utr=utr or str(rnd.randint(10**11, 10**12 - 1)), payer_name_masked=TRAVELLERS[i][1],
                 payee_name="BMRCL Namma Metro", status_text="Payment Successful", app_name=rnd.choice(APPS),
                 bank_name=bank or rnd.choice(BANKS))
        if exact: f["order_id"] = oid
        return f

    def tick(oid, tid, o, d, fare, at_extra=None):
        f = dict(ticket_id=tid, qr_payload="NMQR-" + hexs(96), origin_station=o, destination_station=d,
                 fare=fare, status_text="Valid till end of service today", app_name="Namma Metro WhatsApp")
        if exact: f["order_id"] = oid
        return f

    # ---- S1: clean linked journeys (4 travellers), T1 also has a bank SMS (corroboration)
    clean = {}
    for i in range(4):
        at = t0 + timedelta(minutes=7 * i)
        o, d = rnd.sample(STATIONS, 2); fare = rnd.choice([20, 30, 40, 50])
        oid, tid = f"NMW{rnd.randint(10**7, 10**8-1)}", f"TKT{rnd.randint(10**8, 10**9-1)}"
        p = add(sid(i), "UPI_SUCCESS", at, pay(i, at, fare, oid), "clean_journey")
        t = add(sid(i), "TICKET_QR", at + timedelta(seconds=42), tick(oid, tid, o, d, fare), "clean_journey")
        clean[i] = (p, t, tid, oid, fare, at, o, d)
        extra = []
        if i == 0:
            utr = it[-2]["fields"]["utr"]
            s = add(sid(i), "BANK_SMS", at + timedelta(seconds=20),
                    dict(amount=fare, utr=utr, bank_name=it[-2]["fields"]["bank_name"], status_text="debited"),
                    "clean_journey"); extra.append(s)
        if exact:
            r = link(t, p, "EXACT", ["order_id"], 1.0, "Shared order_id")
        else:
            r = link(t, p, "INFERRED", ["amount", "timestamp_window", "same_sender"], 0.8,
                     "Amount equal, 42s apart, same sender; no shared identifier")
        gt[t].update(expected_rels=[{"to": p, "type": "EXACT" if exact else "INFERRED"}],
                     expected_decision_support="clear" if exact else "needs_review",
                     expected_evidence_level="corroborated" if extra else "extracted")
        if extra:
            link(s, p, "EXACT", ["utr"], 1.0, "Shared UTR"); gt[s]["expected_rels"] = [{"to": p, "type": "EXACT"}]

    # ---- S2: payment, bot error, no ticket -> case
    i = 4; at = t0 + timedelta(minutes=40); oid = f"NMW{rnd.randint(10**7, 10**8-1)}"
    p = add(sid(i), "UPI_SUCCESS", at, pay(i, at, 40, oid), "payment_no_ticket")
    b = add(sid(i), "BOT_ERROR", at + timedelta(seconds=30),
            dict(amount=40, status_text="Booking failed. Amount will be refunded within 7 working days",
                 app_name="Namma Metro WhatsApp", **({"order_id": oid} if exact else {})), "payment_no_ticket")
    if exact:
        link(b, p, "EXACT", ["order_id"], 1.0, "Shared order_id")
    else:
        link(b, p, "INFERRED", ["amount", "timestamp_window", "same_sender"], 0.75, "Amount equal, 30s apart")
    cases.append({"kind": "case", "case_id": nid("cs"), "ref": "CASE-0001", "trip_id": "trip_001",
                  "sender_id": sid(i), "evidence": [p, b], "opened_at": iso(at + timedelta(hours=2)),
                  "state": "case_opened", "last_action": "auto_opened: payment_seen, no ticket_seen",
                  "created_at": iso(at + timedelta(hours=2)), "supersedes": None})
    gt[p].update(expected_case="CASE-0001", expected_decision_support="needs_review")
    gt[b].update(expected_decision_support="needs_review")

    # ---- S2b: same, but refund evidence arrives (refund_evidence_seen)
    i = 5; at = t0 + timedelta(minutes=55); oid = f"NMW{rnd.randint(10**7, 10**8-1)}"
    p = add(sid(i), "UPI_SUCCESS", at, pay(i, at, 30, oid), "refund_seen")
    utr = it[-1]["fields"]["utr"]
    b = add(sid(i), "BOT_ERROR", at + timedelta(seconds=25),
            dict(amount=30, status_text="Booking failed. Amount will be refunded within 7 working days",
                 **({"order_id": oid} if exact else {})), "refund_seen")
    rf = add(sid(i), "REFUND_NOTICE", at + timedelta(days=3, hours=1),
             dict(amount=30, utr=utr, bank_name=it[-2]["fields"]["bank_name"], status_text="credited: refund"),
             "refund_seen")
    link(b, p, "EXACT" if exact else "INFERRED", ["order_id"] if exact else ["amount", "timestamp_window"],
         1.0 if exact else 0.75, "bot error linked to payment")
    link(rf, p, "EXACT", ["utr"], 1.0, "Refund references original UTR")
    cases.append({"kind": "case", "case_id": nid("cs"), "ref": "CASE-0002", "trip_id": "trip_001",
                  "sender_id": sid(i), "evidence": [p, b, rf], "opened_at": iso(at + timedelta(hours=2)),
                  "state": "refund_evidence_seen", "last_action": "refund notice linked by UTR",
                  "created_at": iso(at + timedelta(days=3, hours=1, minutes=1)), "supersedes": None})
    gt[rf].update(expected_rels=[{"to": p, "type": "EXACT"}], expected_case="CASE-0002")

    # ---- S3a: exact resend by SAME sender (same sha256)
    p0, t0e, tid0, *_ = clean[1]
    sha = ev[[e["evidence_id"] for e in ev].index(t0e)]["sha256"]
    dup1 = add(sid(1), "TICKET_QR", t0 + timedelta(hours=1), dict(it[[x["evidence_id"] for x in it].index(t0e)]["fields"]),
               "exact_resend_same_sender", sha=sha,
               phash=ev[[e["evidence_id"] for e in ev].index(t0e)]["phash"])
    gt[dup1].update(expected_flags=["exact_file_dup", "same_sender_resend"], dup_of=t0e,
                    expected_decision_support="clear")  # resend is benign

    # ---- S3b: CROSS-sender reuse of a ticket id (semantic dup) via claim
    _, t2e, tid2, *_r = clean[2]
    at = DAY + timedelta(days=1, hours=11)
    c = add(sid(6), "CLAIM_SUBMISSION", at, dict(ticket_id=tid2, amount=clean[2][4], fare=clean[2][4],
            payer_name_masked=TRAVELLERS[6][1], status_text="Reimbursement claim"), "cross_sender_reuse")
    gt[c].update(expected_flags=["earlier_sighting_other_sender"], dup_of=t2e, expected_decision_support="needs_review")

    # ---- S4: cropped duplicate of T3's ticket by another sender (new sha, phash Hamming 4, id unreadable)
    t3e = clean[3][1]
    ph = ev[[e["evidence_id"] for e in ev].index(t3e)]["phash"]
    flipped = int(ph, 16)
    for b_ in rnd.sample(range(64), 4): flipped ^= (1 << b_)
    cr = add(sid(7), "TICKET_QR", t0 + timedelta(hours=1, minutes=30),
             dict(origin_station=clean[3][6], destination_station=clean[3][7], fare=clean[3][4],
                  status_text="Valid till end of service today"), "cropped_duplicate",
             conf=0.8, tconf=0.7, phash=f"{flipped:016x}")
    gt[cr].update(expected_flags=["perceptual_similar_other_sender", "unreadable_key_field"], dup_of=t3e,
                  phash_hamming=4, expected_decision_support="needs_review")

    # ---- S5: out-of-window ticket (a week earlier)
    at = DAY - timedelta(days=7) + timedelta(hours=10)
    oid = f"NMW{rnd.randint(10**7, 10**8-1)}"; tid = f"TKT{rnd.randint(10**8, 10**9-1)}"
    p = add(sid(0), "UPI_SUCCESS", at, pay(0, at, 40, oid), "out_of_window")
    t = add(sid(0), "TICKET_QR", at + timedelta(seconds=40), tick(oid, tid, "Indiranagar", "MG Road", 40), "out_of_window")
    link(t, p, "EXACT" if exact else "INFERRED", ["order_id"] if exact else ["amount", "timestamp_window"],
         1.0 if exact else 0.8, "linked, but dated before trip window")
    gt[t].update(expected_flags=["date_outside_window"], expected_decision_support="needs_review")

    # ---- S6: inferred-only link even in exact mode (ids missing/unreadable on one side)
    i = 8; at = t0 + timedelta(minutes=80)
    p = add(sid(i), "UPI_SUCCESS", at, pay(i, at, 20, None), "inferred_only")
    tf = tick(None, f"TKT{rnd.randint(10**8, 10**9-1)}", "Majestic", "Cubbon Park", 20); tf.pop("order_id", None)
    t = add(sid(i), "TICKET_QR", at + timedelta(seconds=55), tf, "inferred_only")
    if exact:  # force: this pair has no shared id even in exact mode
        it[[x["evidence_id"] for x in it].index(p)]["fields"]["order_id"] = None
    link(t, p, "INFERRED", ["amount", "timestamp_window", "same_sender"], 0.78, "No shared id; context agrees")
    gt[t].update(expected_rels=[{"to": p, "type": "INFERRED"}], expected_decision_support="needs_review")

    # ---- S7: unmatched refund (no payment anywhere)
    rf = add(sid(9), "REFUND_NOTICE", t0 + timedelta(hours=2),
             dict(amount=60, bank_name="SBI", status_text="credited: refund", utr=str(rnd.randint(10**11, 10**12-1))),
             "unmatched_refund")
    link(rf, rf, "UNMATCHED", [], 0.0, "No payment evidence with matching UTR or amount")
    gt[rf].update(expected_rels=[{"type": "UNMATCHED"}], expected_decision_support="insufficient")

    # ---- S8: suspect (scam-style) notice
    sn = add(sid(4), "SUSPECT_NOTICE", t0 + timedelta(hours=3),
             dict(status_text="Your QR ticket refund has failed. Complete KYC at bmrcl-refund-kyc.example within 24h",
                  payee_name=None), "suspect_notice", tconf=0.88)
    gt[sn].update(expected_flags=["suspect_notice_class"], expected_decision_support="needs_review")

    # ---- S9: ambiguity: two same-amount payments by one sender, one ticket w/o ids
    i = 9; at = t0 + timedelta(hours=4)
    pa = add(sid(i), "UPI_SUCCESS", at, pay(i, at, 40, None), "ambiguous_two_candidates")
    pb = add(sid(i), "UPI_SUCCESS", at + timedelta(seconds=20), pay(i, at, 40, None), "ambiguous_two_candidates")
    tk = tick(None, f"TKT{rnd.randint(10**8, 10**9-1)}", "Trinity", "Halasuruvu", 40); tk.pop("order_id", None)
    t = add(sid(i), "TICKET_QR", at + timedelta(seconds=50), tk, "ambiguous_two_candidates", lang="kn", conf=0.85,
            low=("origin_station",))
    for x in (pa, pb):
        it[[y["evidence_id"] for y in it].index(x)]["fields"]["order_id"] = None
    unm = link(t, t, "UNMATCHED", ["amount", "timestamp_window"], 0.5,
               "Two plausible payments; refusing to guess", candidates=[pa, pb])
    gt[t].update(expected_rels=[{"type": "UNMATCHED", "candidates": [pa, pb]}], expected_decision_support="needs_review",
                 note="Kannada + low-confidence origin_station")

    # ---- Decisions (human). seen_snapshot_hash = hash of subject record at decision time (filled after chain)
    def decision(subject, action, who, reason, when, supersedes=None):
        d = nid("dc")
        dec.append({"kind": "decision", "dec_id": d, "subject_ref": subject, "action": action,
                    "decided_by": who, "reason": reason, "seen_snapshot_hash": None,
                    "created_at": iso(when), "supersedes": supersedes})
        return d

    cw = DAY + timedelta(days=1, hours=12)
    decision(clean[0][1], "approved", "coord_01", "Matches trip roster", cw)
    decision(t_out := gt and [k for k, v in gt.items() if v["scenario"] == "out_of_window"][-1],
             "proof_requested", "coord_01", "Ticket date is before trip window", cw + timedelta(minutes=5))
    # MANUAL link resolves the ambiguity: supersedes the UNMATCHED relationship
    r = nid("rl")
    rel.append({"kind": "relationship", "rel_id": r, "from_id": t, "to_id": pa, "type": "MANUAL",
                "basis": ["coordinator_decision"], "score": 1.0, "reason": "Coordinator linked after asking sender",
                "created_by": "coord_01", "created_at": iso(cw + timedelta(minutes=10)), "supersedes": unm,
                "candidates": None})
    decision(r, "link_manually", "coord_01", "Sender confirmed first payment", cw + timedelta(minutes=10))

    trips = [{"kind": "trip", "trip_id": "trip_001", "name": "Fest volunteers - Saturday",
              "coordinator_id": "coord_01", "join_code": "PRT-4821",
              "window_start": iso(WINDOW[0]), "window_end": iso(WINDOW[1]),
              "created_at": iso(DAY - timedelta(days=2))}]
    trav = [{"kind": "traveller", "traveller_id": sid(i), "trip_id": "trip_001", "display": TRAVELLERS[i][1],
             "created_at": iso(DAY - timedelta(days=1))} for i in range(10)]

    # chain in time order (the chained set = the four record types + cases)
    ledger = sorted(ev + it + rel + cases + dec, key=lambda r: r["created_at"])
    chain(ledger)
    by_id = {r.get("evidence_id") or r.get("rel_id") or r.get("dec_id") or r.get("case_id"): r for r in ledger}
    for d in dec:  # snapshot hash of what the human saw (subject's record_hash) - set AFTER chaining, then re-chain
        d["seen_snapshot_hash"] = by_id.get(d["subject_ref"], {}).get("record_hash")
    chain(ledger)
    return {"meta": {"mode": mode, "seed": seed, "synthetic": True,
                     "note": "All data synthetic. order_id-as-shared-id is an assumption pending Day-0.",
                     "counts": {k: sum(1 for r in ledger if r["kind"] == k) for k in
                                ("evidence", "interpretation", "relationship", "decision", "case")}},
            "trips": trips, "travellers": trav, "ledger": ledger}, gt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["exact", "inferred_only", "both"], default="both")
    ap.add_argument("--out", default=".")
    ap.add_argument("--verify")
    a = ap.parse_args()
    if a.verify:
        ok, i, k, rid = verify(json.load(open(a.verify))["ledger"])
        print("chain OK" if ok else f"BROKEN at index {i} ({k} {rid})"); sys.exit(0 if ok else 1)
    for m in (["exact", "inferred_only"] if a.mode == "both" else [a.mode]):
        data, gt = build(m)
        json.dump(data, open(f"{a.out}/fixtures_{m}.json", "w"), indent=2, ensure_ascii=False)
        json.dump(gt, open(f"{a.out}/ground_truth_{m}.json", "w"), indent=2, ensure_ascii=False)
        print(m, data["meta"]["counts"])
