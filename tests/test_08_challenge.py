import unittest
from datetime import datetime, timedelta, timezone

from tests.common import Base
from pratibimb import challenge as ch, claims as cl, trust
from pratibimb.config import load_config
from pratibimb.fixtures import load_into

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


class TestChallenge(Base):
    def setUp(self):
        super().setUp()
        self.cfg = load_config()

    def load(self, name):
        self.idx = load_into(self.s, only=[name])
        return self.idx[name]["keys"]

    def claim(self, key):
        iid = self.idx_keys[key]["interp_id"]
        return next(c for c in cl.build_claims(self.s, "trip_demo", self.cfg, NOW) if iid in c["interp_ids"])

    def test_no_ticket_asks_for_ticket_and_states_why(self):
        self.idx_keys = self.load("payment_no_ticket")
        c = self.claim("pay")
        row = ch.issue(self.s, "trip_demo", c["claim_ref"], self.cfg, NOW)
        self.assertEqual((row["attribute"], row["request_type"], row["reason_code"]),
                         ("ticket_issued", "ticket_with_status_bar", "no_ticket_seen"))
        self.assertIn("no ticket has been seen", row["message"])
        self.assertIn("nothing is rejected", row["message"])
        for bad in ("fraud", "verified"):
            self.assertNotIn(bad, row["message"].lower())

    def test_issue_is_idempotent(self):
        self.idx_keys = self.load("payment_no_ticket")
        ref = self.claim("pay")["claim_ref"]
        a = ch.issue(self.s, "trip_demo", ref, self.cfg, NOW)
        b = ch.issue(self.s, "trip_demo", ref, self.cfg, NOW)
        self.assertEqual(a["challenge_id"], b["challenge_id"])
        self.assertEqual(len(self.s.current_challenges()), 1)

    def test_inferred_link_asks_for_bank_sms(self):
        self.idx_keys = self.load("inferred_only_link")
        row = ch.issue(self.s, "trip_demo", self.claim("pay")["claim_ref"], self.cfg, NOW)
        self.assertEqual((row["request_type"], row["reason_code"]), ("bank_sms", "link_by_amount_time_only"))

    def test_clear_claim_is_not_challenged(self):
        self.idx_keys = self.load("clean_linked_journey")
        with self.assertRaises(Exception):
            ch.issue(self.s, "trip_demo", self.claim("pay")["claim_ref"], self.cfg, NOW)

    def test_no_response_path_never_rejects(self):
        self.idx_keys = self.load("payment_no_ticket")
        c = self.claim("pay")
        row = ch.issue(self.s, "trip_demo", c["claim_ref"], self.cfg, NOW)
        self.assertEqual(ch.expire(self.s, "trip_demo", NOW), [])      # not due yet
        later = NOW + timedelta(hours=self.cfg["challenge_response_hours"] + 1)
        out = ch.expire(self.s, "trip_demo", later)
        self.assertEqual([o["status"] for o in out], ["no_response"])
        self.assertEqual(self.s.counts()["decisions"], 0, "expiry must not write a Decision")
        c2 = self.claim("pay")
        a = trust.assess(self.s, c2, self.cfg, self.s.get_trip("trip_demo"))
        self.assertEqual(a["decision_support"], "needs_review")
        self.assertIn("challenge_no_response", [s["code"] for s in a["signals"]])
        self.assertFalse(c2["resolved"])
        self.assertEqual(ch.expire(self.s, "trip_demo", later), [], "expiring twice changes nothing")

    def test_response_links_through_normal_chain(self):
        self.idx_keys = self.load("payment_no_ticket")
        c = self.claim("pay")
        row = ch.issue(self.s, "trip_demo", c["claim_ref"], self.cfg, NOW)
        from tests.common import add_ev, add_in
        ev = add_ev(self.s, sender_id="s_ravi", trip_id="trip_demo", sha256="c" * 64, phash="cd" * 8)
        add_in(self.s, ev, screenshot_type="TICKET_QR", fields={"ticket_id": "T9"}, field_confidence={"ticket_id": 0.9},
               field_source={"ticket_id": "qr_decoder"})
        done = ch.auto_respond(self.s, "trip_demo", self.cfg)
        self.assertEqual([d["status"] for d in done], ["responded"])
        self.assertEqual(done[0]["response_evidence_id"], ev)
        self.assertEqual(self.s.current_challenges(subject_ref=row["subject_ref"])[0]["status"], "responded")
        with self.assertRaises(Exception):
            ch.respond(self.s, row["challenge_id"], ev)     # superseded row cannot be answered twice
        self.assertTrue(self.s.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
