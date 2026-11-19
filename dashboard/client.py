"""
Data layer for the dashboard. Two interchangeable clients with the SAME methods:

  FixtureClient(path, truth_path)  - works today from Member B's fixtures (offline)
  ApiClient(base_url)              - Member B's live FastAPI (endpoints per contract 1.4)

Everything the UI shows comes through these methods, so switching to the live API
is a sidebar toggle, not a rewrite. Response shapes are documented in
docs/api_assumptions.md - confirm them with B on Day 2.

Fixture mode DERIVES the inbox from B's ground-truth file (expected flags /
decision_support). It is a stand-in for B's trust assessment, not a reimplementation.
"""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LEVELS = ["extracted", "corroborated", "independently_verified"]
FLAG_REASONS = {  # structured flag -> plain reason (B emits flags; A translates; this is the EN fallback)
    "exact_file_dup": "Same file was sent before",
    "same_sender_resend": "Resend by the same person",
    "earlier_sighting_other_sender": "This ticket ID was already seen from a different sender",
    "perceptual_similar_other_sender": "Image looks similar to another sender's evidence (similarity signal only)",
    "unreadable_key_field": "A key field could not be read",
    "date_outside_window": "Date is outside the trip window",
    "suspect_notice_class": "Message looks like a refund/KYC-style notice, not an official one",
}


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def H(s):
    return hashlib.sha256(s.encode()).hexdigest()


def verify_chain(ledger):
    """Same rule as B's generator: record_hash = H(canon(record minus record_hash) + prev_hash)."""
    prev = "GENESIS"
    for i, r in enumerate(ledger):
        body = {k: v for k, v in r.items() if k != "record_hash"}
        if r.get("prev_hash") != prev or H(canon(body) + prev) != r.get("record_hash"):
            return {"ok": False, "broken_index": i, "kind": r.get("kind"), "length": len(ledger)}
        prev = r["record_hash"]
    return {"ok": True, "broken_index": None, "kind": None, "length": len(ledger)}


def mask_utr(u):
    return None if not u else "*" * (len(str(u)) - 4) + str(u)[-4:]


def _rid(r):
    return r.get("evidence_id") or r.get("interp_id") or r.get("rel_id") or r.get("dec_id") or r.get("case_id")


class FixtureClient:
    mode = "fixture"

    def __init__(self, path, truth_path=None):
        d = json.load(open(path))
        self.meta, self.trips, self.travellers = d["meta"], d["trips"], d["travellers"]
        self.ledger = copy.deepcopy(d["ledger"])
        self.gt = json.load(open(truth_path)) if truth_path and Path(truth_path).exists() else {}

    # ---------- indexes (cheap; ledger is small) ----------
    def _by(self, kind):
        return [r for r in self.ledger if r["kind"] == kind]

    def _current(self, recs, idkey):
        sup = {r["supersedes"] for r in recs if r.get("supersedes")}
        return [r for r in recs if r[idkey] not in sup]

    def _ev(self):
        return {e["evidence_id"]: e for e in self._by("evidence")}

    def _interp(self):
        cur = self._current(self._by("interpretation"), "interp_id")
        return {i["evidence_id"]: i for i in cur}

    def _rels(self):
        return self._current(self._by("relationship"), "rel_id")

    def _decs(self):
        return self._current(self._by("decision"), "dec_id")

    def _cases(self):
        return self._by("case")

    def _trip(self, trip_id):
        return next(t for t in self.trips if t["trip_id"] == trip_id)

    def _name(self, sender):
        return next((t["display"] for t in self.travellers if t["traveller_id"] == sender), sender)

    @staticmethod
    def _in_window(ts, trip):
        return trip["window_start"] <= ts <= trip["window_end"]

    # ---------- record-level helpers ----------
    def _rel_from(self, eid):
        rs = [r for r in self._rels() if r["from_id"] == eid]
        return rs[-1] if rs else None

    def _decisions_for(self, eid):
        subjects = {eid} | {r["rel_id"] for r in self._rels() if r["from_id"] == eid}
        return sorted([d for d in self._decs() if d["subject_ref"] in subjects], key=lambda d: d["created_at"])

    def _attr_levels(self, eid):
        """Per-attribute levels. Never 'independently_verified' without an external source (we have none)."""
        it = self._interp()
        typ = it[eid]["screenshot_type"]
        rel = self._rel_from(eid)
        target = rel["to_id"] if rel and rel["type"] in ("EXACT", "INFERRED", "MANUAL") and rel["to_id"] != eid else None
        pay = target if target and it[target]["screenshot_type"] == "UPI_SUCCESS" else (eid if typ == "UPI_SUCCESS" else None)
        pay_level = "none"
        if pay:
            pay_level = "extracted"
            for r in self._rels():  # a bank SMS linked EXACT to this payment => corroborated debit
                if r["type"] == "EXACT" and r["to_id"] == pay and it[r["from_id"]]["screenshot_type"] == "BANK_SMS":
                    pay_level = "corroborated"
        tick = "extracted" if typ in ("TICKET_QR", "CLAIM_SUBMISSION") else "none"
        return {"payment_debit": pay_level, "ticket_issued": tick}

    def _assess(self, eid):
        g = self.gt.get(eid, {})
        rel = self._rel_from(eid)
        flags = list(g.get("expected_flags", []))
        reasons = [FLAG_REASONS[f] for f in flags if f in FLAG_REASONS]
        rel_in = next((r for r in self._rels() if r["to_id"] == eid and r["from_id"] != eid
                       and r["type"] != "UNMATCHED"), None)   # evidence that others link TO (e.g. a payment)
        rtype = rel["type"] if rel else (rel_in["type"] if rel_in else "UNMATCHED")
        if rel is None and rel_in is None and not g.get("expected_flags"):
            reasons.append("No matching evidence found; kept, not forced into a link")
        if rel and rel["type"] == "INFERRED":
            reasons.append("Linked by context only (no shared identifier); never auto-cleared")
        if rel and rel["type"] == "UNMATCHED":
            cands = rel.get("candidates")
            reasons.append(f"Two plausible matches ({', '.join(cands)}); not guessed" if cands
                           else "No matching evidence found; kept, not forced into a link")
        case = next((c for c in self._cases() if eid in c["evidence"] and c["state"] == "case_opened"), None)
        if case:
            reasons.append(f"Payment seen, no ticket ({case['ref']}); refund evidence not seen yet")
        ds = g.get("expected_decision_support")
        if ds is None:
            ds = "needs_review" if (rtype in ("INFERRED", "UNMATCHED") or flags) else "clear"
        if not reasons and ds != "clear":
            reasons.append("Needs a human look")
        earlier = None
        if g.get("dup_of"):
            o = self._ev()[g["dup_of"]]
            earlier = {"evidence_id": o["evidence_id"], "sender": self._name(o["sender_id"]),
                       "date": o["received_at"][:10]}
        return {"decision_support": ds, "reasons": reasons, "relationship_type": rtype,
                "evidence_level": self._attr_levels(eid), "earlier_sighting": earlier,
                "case_ref": case["ref"] if case else g.get("expected_case")}

    # ---------- public API (mirrors B's endpoints) ----------
    def trips_list(self):
        return self.trips

    def summary(self, trip_id):
        trip, ev, it = self._trip(trip_id), self._ev(), self._interp()
        rows = []
        for t in [x for x in self.travellers if x["trip_id"] == trip_id]:
            mine = [e for e in ev.values() if e["sender_id"] == t["traveller_id"]
                    and self._in_window(it[e["evidence_id"]]["fields"]["timestamp"], trip)]
            pays = [e for e in mine if it[e["evidence_id"]]["screenshot_type"] == "UPI_SUCCESS"]
            ticks = [e for e in mine if it[e["evidence_id"]]["screenshot_type"] == "TICKET_QR"]
            link = None
            for tk in ticks:
                r = self._rel_from(tk["evidence_id"])
                if r:
                    link = r["type"]
            open_case = any(c["sender_id"] == t["traveller_id"] and c["state"] == "case_opened" for c in self._cases())
            state = ("stuck" if (open_case and not ticks) else
                     "ready" if link in ("EXACT", "MANUAL") else
                     "pending" if (ticks or pays) else "no evidence yet")
            last = [d for e in mine for d in self._decisions_for(e["evidence_id"])]
            last = sorted(last, key=lambda d: d["created_at"])[-1]["action"] if last else None
            rows.append({"traveller": t["display"], "payment_seen": bool(pays), "ticket_seen": bool(ticks),
                         "link_type": link, "state_machine_observed": state,
                         "traveller_asserts_travel": None,  # self-report; not captured in fixtures
                         "coordinator_decision": last})
        counts = {k: sum(r["state_machine_observed"] == k for r in rows)
                  for k in ("ready", "pending", "stuck", "no evidence yet")}
        return {"trip": trip, "counts": counts, "roster": rows}

    def inbox(self, trip_id):
        ev, it = self._ev(), self._interp()
        skip = {e for c in self._cases() for e in c["evidence"][1:]}   # one row per case
        items, total = [], 0
        for eid, e in ev.items():
            if e["trip_id"] != trip_id:
                continue
            total += 1
            if eid in skip:
                continue
            # a payment linked from a ticket is reviewed via that ticket's row (one row per journey)
            if any(r["to_id"] == eid and r["from_id"] != eid and it[r["from_id"]]["screenshot_type"] == "TICKET_QR"
                   and r["type"] != "UNMATCHED" for r in self._rels()):
                continue
            a = self._assess(eid)
            decs = self._decisions_for(eid)
            resolved = any(d["action"] in ("approved", "rejected", "link_manually") for d in decs)
            if a["decision_support"] == "clear" or resolved:
                continue
            f = it[eid]["fields"]
            items.append({"evidence_id": eid, "screenshot_type": it[eid]["screenshot_type"],
                          "sender": self._name(e["sender_id"]), "amount": f.get("amount") or f.get("fare"),
                          "route": f"{f['origin_station']} -> {f['destination_station']}" if f.get("origin_station") else None,
                          "status": "proof requested" if any(d["action"] == "proof_requested" for d in decs) else "open",
                          **a})
        return {"needs_review": len(items), "total_screenshots": total, "items": items}

    def trail(self, record_id):
        e = self._ev()[record_id]
        rels = [r for r in self._by("relationship") if record_id in (r["from_id"], r["to_id"])]
        relids = {r["rel_id"] for r in rels}
        decs = [d for d in self._by("decision") if d["subject_ref"] == record_id or d["subject_ref"] in relids]

        def m(f):
            f = dict(f)
            f["utr"] = mask_utr(f.get("utr"))
            return f

        interps = [{**i, "fields": m(i["fields"])} for i in self._by("interpretation") if i["evidence_id"] == record_id]
        return {"evidence": {k: v for k, v in e.items() if k != "file_ref"},  # no image path by default
                "interpretations": interps, "relationships": rels, "decisions": decs,
                "later_changes": [f"{x['kind']} {_rid(x)} supersedes {x['supersedes']}"
                                  for x in rels + decs + interps if x.get("supersedes")]}

    def post_decision(self, subject_ref, action, decided_by, reason, link_to=None):
        assert action in ("approved", "proof_requested", "rejected", "link_manually")
        now = datetime.now(timezone.utc).isoformat()
        by = {_rid(r): r for r in self.ledger}
        seen = by[subject_ref]["record_hash"] if subject_ref in by else None
        recs = []
        if action == "link_manually" and link_to:
            old = self._rel_from(subject_ref)
            recs.append({"kind": "relationship", "rel_id": f"rl_new_{len(self.ledger)}", "from_id": subject_ref,
                         "to_id": link_to, "type": "MANUAL", "basis": ["coordinator_decision"], "score": 1.0,
                         "reason": reason, "created_by": decided_by, "created_at": now,
                         "supersedes": old["rel_id"] if old else None, "candidates": None})
        dec = {"kind": "decision", "dec_id": f"dc_new_{len(self.ledger) + len(recs)}", "subject_ref": subject_ref,
               "action": action, "decided_by": decided_by, "reason": reason, "seen_snapshot_hash": seen,
               "created_at": now, "supersedes": None}
        recs.append(dec)
        for r in recs:  # append-only: new record chained onto the tail, nothing rewritten
            r["prev_hash"] = self.ledger[-1]["record_hash"]
            r["record_hash"] = H(canon({k: v for k, v in r.items() if k != "record_hash"}) + r["prev_hash"])
            self.ledger.append(r)
        return dec

    def audit_verify(self):
        return verify_chain(self.ledger)

    def tamper_demo(self):
        """Edit one past row in a COPY (never the live ledger) and re-run the check."""
        t = copy.deepcopy(self.ledger)
        i = next(n for n, r in enumerate(t) if r["kind"] == "interpretation" and r["fields"].get("amount"))
        t[i]["fields"]["amount"] = t[i]["fields"]["amount"] + 100
        return {"edited_index": i, "edited": f"{_rid(t[i])}.fields.amount", "result": verify_chain(t)}

    def claims(self, trip_id):
        ev, it = self._ev(), self._interp()
        order = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}
        rows = []
        for eid, e in ev.items():
            typ = it[eid]["screenshot_type"]
            case = next((c for c in self._cases() if c["evidence"][0] == eid and c["state"] == "case_opened"), None)
            if typ not in ("TICKET_QR", "CLAIM_SUBMISSION") and not case:
                continue
            f = it[eid]["fields"]
            rel = self._rel_from(eid)
            a = self._assess(eid)
            pay = None
            if rel and rel["to_id"] in it and rel["to_id"] != eid:
                pay = it[rel["to_id"]]["fields"] if it[rel["to_id"]]["screenshot_type"] == "UPI_SUCCESS" else None
            if case:
                pay = f
            ds = self._decisions_for(eid)
            lv = a["evidence_level"]
            rows.append({"traveller": self._name(e["sender_id"]), "date": f["timestamp"][:10],
                         "route": f"{f['origin_station']} -> {f['destination_station']}" if f.get("origin_station") else "",
                         "fare": f.get("fare") or f.get("amount"), "ticket_reference": f.get("ticket_id") or "",
                         "payment_reference": mask_utr(pay.get("utr")) if pay else "",
                         "relationship_type": rel["type"] if rel else "UNMATCHED",
                         "evidence_level": f"payment_debit: {lv['payment_debit']}; ticket_issued: {lv['ticket_issued']}",
                         "flags_with_reasons": " | ".join(a["reasons"]),
                         "coordinator_decision": ds[-1]["action"] if ds else "",
                         "decision_time": ds[-1]["created_at"] if ds else "", "evidence_id": eid})
        return sorted(rows, key=lambda r: (order[r["relationship_type"]], r["date"]))


class ApiClient:
    """Live client for Member B's FastAPI. Shapes: docs/api_assumptions.md."""
    mode = "api"

    def __init__(self, base_url):
        import requests
        self.s, self.base = requests, base_url.rstrip("/")

    def _get(self, p, **kw):
        r = self.s.get(self.base + p, params=kw or None, timeout=15)
        r.raise_for_status()
        return r.json()

    def trips_list(self): return self._get("/trips")
    def summary(self, trip_id): return self._get(f"/trips/{trip_id}/summary")
    def inbox(self, trip_id): return self._get(f"/trips/{trip_id}/inbox")
    def trail(self, record_id): return self._get(f"/records/{record_id}/trail")
    def audit_verify(self): return self._get("/audit/verify")
    def claims(self, trip_id):
        res = self._get("/export/claims", trip_id=trip_id)
        if isinstance(res, dict):
            return res.get("rows", res.get("claims", []))
        return res

    def post_decision(self, subject_ref, action, decided_by, reason, link_to=None):
        r = self.s.post(self.base + "/decisions", json={"subject_ref": subject_ref, "action": action,
                        "decided_by": decided_by, "reason": reason, "link_to": link_to}, timeout=15)
        r.raise_for_status()
        return r.json()

    def tamper_demo(self):
        return {"edited": "(run B's tamper script on the server, then press 'Run chain check')",
                "result": self.audit_verify()}


# =====================================================================================================
# SyntheticClient: runs the dashboard on data/ (30 synthetic screenshots, B-style ledger built in memory).
#   * Relationships are the corpus's AUTHORED expected relationships (relationships.json), seeded like B's fixtures.
#   * Flags, reasons, evidence levels and clear/needs_review come from standin/engine.py (rules, no labels).
#   * Everything is synthetic; nothing here is a measured result.
# =====================================================================================================
import sys as _sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
from standin import engine as _engine  # noqa: E402
from standin.dataset import load as _load_dataset  # noqa: E402

_REL_ORDER = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}
_STATES = ("ready", "needs review", "pending", "stuck", "no evidence yet")


class SyntheticClient:
    mode = "fixture"
    can_show_images = True          # synthetic, watermarked images only; every view is written to access_log

    def __init__(self, data_dir=None):
        D = _load_dataset(data_dir) if data_dir else _load_dataset()
        self.D, self.recs = D, {r["evidence_id"]: r for r in D["records"]}
        self.trips = [{"trip_id": t["trip_id"], "name": f"Synthetic trip {t['service_date']} ({t['split']})",
                       "window_start": t["window_start"], "window_end": t["window_end"], "split": t["split"]}
                      for t in D["trips"]]
        self.access_log = []
        ordered = sorted(D["records"], key=_engine.key)
        seq = []
        for r in ordered:
            seq.append({"kind": "evidence", "evidence_id": r["evidence_id"], "trip_id": r["trip_id"], "sender_id": r["sender_id"],
                        "channel": r["channel"], "received_at": r["received_at"], "file_ref": str(D["dir"] / r["image_file"]),
                        "sha256": r["sha256"], "phash": r["phash"], "ahash": r["ahash"], "status": "received"})
            seq.append({"kind": "interpretation", "interp_id": f"ip_{r['evidence_id']}", "evidence_id": r["evidence_id"],
                        "producer": "dataset_ground_truth", "model_version": D["manifest"]["schema_version"], "sarvam_job_id": None,
                        "screenshot_type": r["screenshot_type"], "type_confidence": None, "fields": dict(r["all_fields"]),
                        "field_confidence": None, "raw_text_ref": None, "language_detected": r["language"],
                        "created_at": r["received_at"], "supersedes": None})
        for x in D["relationships"]:
            seq.append({"kind": "relationship", "rel_id": x["relationship_id"], "from_id": x["from_evidence_id"],
                        "to_id": x["to_evidence_id"], "type": x["type"], "basis": x["basis"], "score": None, "reason": x["reason"],
                        "created_by": "fixture_seed", "created_at": self.recs[x["from_evidence_id"]]["received_at"],
                        "supersedes": None, "candidates": None})
        obs = [_engine.observable(r) for r in D["records"]]
        links0 = [self._link(x) for x in seq if x["kind"] == "relationship"]
        a0 = _engine.analyse(obs, self.trips, links=links0)
        for ref in sorted({a["case_ref"] for a in a0.values() if a["case_ref"]}):
            ev = sorted([e for e, a in a0.items() if a["case_ref"] == ref], key=lambda e: _engine.key(self.recs[e]))
            ev = sorted(ev, key=lambda e: 0 if self.recs[e]["screenshot_type"] == "UPI_FAILED_PENDING" else 1)
            seq.append({"kind": "case", "case_id": ref, "ref": ref, "state": "case_opened", "evidence": ev,
                        "sender_id": self.recs[ev[0]]["sender_id"], "created_at": self.recs[ev[0]]["received_at"]})
        self.ledger, prev = [], "GENESIS"
        for r in seq:
            r["prev_hash"] = prev
            r["record_hash"] = H(canon({k: v for k, v in r.items() if k != "record_hash"}) + prev)
            prev = r["record_hash"]
            self.ledger.append(r)

    # ---------- small helpers ----------
    @staticmethod
    def _link(r):
        return {"from": r["from_id"], "to": r["to_id"], "type": r["type"], "basis": r.get("basis") or [],
                "reason": r.get("reason", ""), "candidates": r.get("candidates")}

    def _by(self, kind):
        return [r for r in self.ledger if r["kind"] == kind]

    def _current(self, recs, idkey):
        sup = {r["supersedes"] for r in recs if r.get("supersedes")}
        return [r for r in recs if r[idkey] not in sup]

    def _rels(self):
        return self._current(self._by("relationship"), "rel_id")

    def _decs(self):
        return self._current(self._by("decision"), "dec_id")

    def _cases(self):
        return self._by("case")

    def _asm(self):
        obs = [_engine.observable(r) for r in self.D["records"]]
        return _engine.analyse(obs, self.trips, links=[self._link(r) for r in self._rels()])

    def _name(self, sender):
        return "Traveller " + sender.rsplit("-", 1)[-1]

    def _decisions_for(self, eid):
        subjects = {eid} | {r["rel_id"] for r in self._rels() if r["from_id"] == eid}
        return sorted([d for d in self._decs() if d["subject_ref"] in subjects], key=lambda d: d["created_at"])

    def _trip_items(self, trip_id):
        return sorted([r for r in self.D["records"] if r["trip_id"] == trip_id], key=_engine.key)

    def _case_skip(self):
        return {e for c in self._cases() for e in c["evidence"][1:]}

    def _resolved(self, eid):
        return any(d["action"] in ("approved", "rejected", "link_manually") for d in self._decisions_for(eid))

    # ---------- public API (mirrors B's endpoints) ----------
    def trips_list(self):
        return self.trips

    def inbox(self, trip_id):
        asm, skip = self._asm(), self._case_skip()
        items, items_all = [], self._trip_items(trip_id)
        hidden_other = 0
        for r in items_all:
            eid, a = r["evidence_id"], asm[r["evidence_id"]]
            if r["screenshot_type"] == "OTHER":
                hidden_other += 1
                continue
            if a["decision_support"] == "clear" or eid in skip or a["reviewed_via"] or self._resolved(eid):
                continue
            decs = self._decisions_for(eid)
            f = r["all_fields"]
            es = a["earlier_sighting"]
            items.append({"evidence_id": eid, "screenshot_type": r["screenshot_type"], "sender": self._name(r["sender_id"]),
                          "amount": f.get("amount") or f.get("fare"),
                          "route": f"{f['origin_station']} -> {f['destination_station']}" if f.get("origin_station") else None,
                          "status": "proof requested" if any(d["action"] == "proof_requested" for d in decs) else "open",
                          "decision_support": a["decision_support"], "reasons": a["reasons"],
                          "relationship_type": a["relationship_type"], "evidence_level": a["evidence_level"],
                          "earlier_sighting": ({"evidence_id": es["evidence_id"], "sender": self._name(es["sender_id"]), "date": es["date"]}
                                               if es else None), "case_ref": a["case_ref"]})
        return {"needs_review": len(items), "total_screenshots": len(items_all), "not_claim_related": hidden_other, "items": items}

    def summary(self, trip_id):
        asm, trip = self._asm(), next(t for t in self.trips if t["trip_id"] == trip_id)
        in_inbox = {i["evidence_id"] for i in self.inbox(trip_id)["items"]}
        rows, items_all = [], self._trip_items(trip_id)
        for s in sorted({r["sender_id"] for r in items_all}):
            mine = [r for r in items_all if r["sender_id"] == s]
            ids = {r["evidence_id"] for r in mine}
            pays = [r for r in mine if r["screenshot_type"] in _engine.PAYMENTS]
            ticks = [r for r in mine if r["screenshot_type"] == "TICKET_QR"]
            link = None
            for r in mine:
                l = asm[r["evidence_id"]]["link"]
                if l and (r["screenshot_type"] == "UPI_SUCCESS" or (link is None and r["screenshot_type"] == "BANK_SMS")):
                    link = l["type"]
            case = any(c["sender_id"] == s for c in self._cases())
            flagged = bool(ids & in_inbox) or any(
                asm[e]["decision_support"] != "clear" and asm[e]["reviewed_via"] and asm[e]["reviewed_via"] in in_inbox for e in ids)
            state = ("stuck" if (case and not any(t for t in ticks)) else "needs review" if flagged else
                     "ready" if link in ("EXACT", "MANUAL") else "pending" if (ticks or pays) else "no evidence yet")
            last = sorted([d for e in ids for d in self._decisions_for(e)], key=lambda d: d["created_at"])
            rows.append({"traveller": self._name(s), "payment_seen": bool(pays), "ticket_seen": bool(ticks), "link_type": link,
                         "state_machine_observed": state, "traveller_asserts_travel": None,
                         "coordinator_decision": last[-1]["action"] if last else None})
        counts = {k: sum(r["state_machine_observed"] == k for r in rows) for k in _STATES}
        return {"trip": trip, "counts": counts, "roster": rows}

    def trail(self, record_id):
        e = next(r for r in self._by("evidence") if r["evidence_id"] == record_id)
        rels = [r for r in self._by("relationship") if record_id in (r["from_id"], r["to_id"])]
        relids = {r["rel_id"] for r in rels}
        decs = [d for d in self._by("decision") if d["subject_ref"] == record_id or d["subject_ref"] in relids]

        def m(f):
            f = dict(f)
            f["utr"] = mask_utr(f.get("utr"))
            return f

        interps = [{**i, "fields": m(i["fields"])} for i in self._by("interpretation") if i["evidence_id"] == record_id]
        return {"evidence": {k: v for k, v in e.items() if k != "file_ref"}, "interpretations": interps,
                "relationships": rels, "decisions": decs,
                "later_changes": [f"{x['kind']} {_rid(x)} supersedes {x['supersedes']}" for x in rels + decs + interps if x.get("supersedes")]}

    def image_path(self, evidence_id, requested_by, reason):
        """Raw-image access is a separate, logged action (synthetic watermarked images only)."""
        if not (reason or "").strip():
            raise ValueError("a reason is required")
        self.access_log.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "who": requested_by,
                                "evidence_id": evidence_id, "reason": reason.strip()})
        return next(r for r in self._by("evidence") if r["evidence_id"] == evidence_id)["file_ref"]

    def post_decision(self, subject_ref, action, decided_by, reason, link_to=None):
        assert action in ("approved", "proof_requested", "rejected", "link_manually")
        now = datetime.now(timezone.utc).isoformat()
        by = {_rid(r): r for r in self.ledger}
        seen = by[subject_ref]["record_hash"] if subject_ref in by else None
        recs = []
        if action == "link_manually" and link_to:
            old = next((r for r in self._rels() if r["from_id"] == subject_ref), None)
            recs.append({"kind": "relationship", "rel_id": f"rl_new_{len(self.ledger)}", "from_id": subject_ref, "to_id": link_to,
                         "type": "MANUAL", "basis": ["coordinator_decision"], "score": 1.0, "reason": reason, "created_by": decided_by,
                         "created_at": now, "supersedes": old["rel_id"] if old else None, "candidates": None})
        recs.append({"kind": "decision", "dec_id": f"dc_new_{len(self.ledger) + len(recs)}", "subject_ref": subject_ref, "action": action,
                     "decided_by": decided_by, "reason": reason, "seen_snapshot_hash": seen, "created_at": now, "supersedes": None})
        for r in recs:
            r["prev_hash"] = self.ledger[-1]["record_hash"]
            r["record_hash"] = H(canon({k: v for k, v in r.items() if k != "record_hash"}) + r["prev_hash"])
            self.ledger.append(r)
        return recs[-1]

    def audit_verify(self):
        return verify_chain(self.ledger)

    def tamper_demo(self):
        t = copy.deepcopy(self.ledger)
        i = next(n for n, r in enumerate(t) if r["kind"] == "interpretation" and r["fields"].get("amount"))
        t[i]["fields"]["amount"] = "9999.00"
        return {"edited_index": i, "edited": f"{_rid(t[i])}.fields.amount", "result": verify_chain(t)}

    def demo_cases(self):
        return self.D["demo_cases"]

    def claims(self, trip_id):
        asm, rows, recs = self._asm(), [], self.recs
        cases_first = {c["evidence"][0] for c in self._cases()}
        for r in self._trip_items(trip_id):
            eid, typ = r["evidence_id"], r["screenshot_type"]
            if typ not in ("TICKET_QR", "CLAIM_SUBMISSION") and eid not in cases_first:
                continue
            a, f = asm[eid], r["all_fields"]
            pay = None
            if eid in cases_first:
                pay = f
            else:
                tk = eid
                if typ == "CLAIM_SUBMISSION" and a["link"]:
                    tk = a["link"]["to"]
                l = next((l for l in (self._link(x) for x in self._rels()) if l["to"] == tk and recs[l["from"]]["screenshot_type"] == "UPI_SUCCESS"
                          and l["type"] in ("EXACT", "INFERRED")), None)
                pay = recs[l["from"]]["all_fields"] if l else None
            ds = self._decisions_for(eid)
            lv = a["evidence_level"]
            rows.append({"traveller": self._name(r["sender_id"]), "date": (f.get("timestamp") or r["received_at"])[:10],
                         "route": f"{f['origin_station']} -> {f['destination_station']}" if f.get("origin_station") else "",
                         "fare": f.get("fare") or f.get("amount"), "ticket_reference": f.get("ticket_id") or "",
                         "payment_reference": (mask_utr(pay.get("utr")) if pay else None) or "",
                         "relationship_type": a["relationship_type"],
                         "evidence_level": f"payment_debit: {lv['payment_debit']}; ticket_issued: {lv['ticket_issued']}",
                         "flags_with_reasons": " | ".join(a["reasons"]), "decision_support": a["decision_support"],
                         "coordinator_decision": ds[-1]["action"] if ds else "", "decision_time": ds[-1]["created_at"] if ds else "",
                         "evidence_id": eid})
        return sorted(rows, key=lambda x: (_REL_ORDER[x["relationship_type"]], x["date"]))
