import json
import os
import subprocess
import sys
import unittest

from tests.common import *  # noqa
from pratibimb.enums import FIELD_KEYS, REL_TYPES
from pratibimb.fixtures import DEFAULT_PATH, load_fixture_file, load_into

REQUIRED = {"clean_linked_journey", "payment_no_ticket", "exact_duplicate_same_sender", "cropped_duplicate",
            "out_of_window_ride", "inferred_only_link", "unmatched_refund", "suspect_notice"}


def ham(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


class TestFixtures(Base):
    def setUp(self):
        super().setUp()
        self.data = load_fixture_file()
        self.sc = {s["name"]: s for s in self.data["scenarios"]}

    def test_all_eight_required_scenarios_present_plus_extras(self):
        self.assertTrue(REQUIRED <= set(self.sc), REQUIRED - set(self.sc))
        self.assertIn("ambiguous_two_candidates", self.sc)
        self.assertIn("manual_link", self.sc)
        self.assertIn("cross_sender_duplicate", self.sc)

    def test_marked_synthetic(self):
        self.assertTrue(self.data["synthetic"])

    def test_loads_and_verifies(self):
        idx = load_into(self.s)
        self.assertEqual(self.s.counts(), {"evidence": 21, "interpretations": 21, "relationships": 9, "decisions": 2})
        res = self.s.verify(expected_length=53)
        self.assertTrue(res["ok"], res)

    def test_each_scenario_loads_alone_into_a_fresh_store(self):
        for name in self.sc:
            with self.subTest(scenario=name):
                s = new_store()
                idx = load_into(s, only=[name])
                self.assertEqual(list(idx), [name])
                self.assertTrue(s.verify()["ok"])
                s.close()

    def test_expected_relationship_types_match_what_was_stored(self):
        idx = load_into(self.s)
        for name, info in idx.items():
            with self.subTest(scenario=name):
                got = sorted(self.s.get(r)["type"] for r in info["relationships"])
                self.assertEqual(got, sorted(info["expect"]["relationship_types"]))

    def test_all_four_relationship_types_are_represented(self):
        load_into(self.s)
        seen = {r["type"] for r in self.s.list_records("relationships")}
        self.assertEqual(seen, set(REL_TYPES))

    def test_every_interpretation_honours_the_contract(self):
        load_into(self.s)
        for r in self.s.list_records("interpretations"):
            self.assertEqual(set(r["fields"]), set(FIELD_KEYS))
            for k, val in r["fields"].items():
                if val is None:
                    self.assertEqual(r["field_confidence"][k], 0.0)
                else:
                    self.assertGreater(r["field_confidence"][k], 0.0)

    def test_exact_duplicate_has_identical_hashes_and_ticket(self):
        items = {i["key"]: i for i in self.sc["exact_duplicate_same_sender"]["items"]}
        a, b = items["first"], items["resend"]
        self.assertEqual((a["sha256"], a["phash"]), (b["sha256"], b["phash"]))
        self.assertEqual(a["interpretation"]["fields"]["ticket_id"], b["interpretation"]["fields"]["ticket_id"])
        self.assertEqual(a["sender_id"], b["sender_id"])

    def test_cropped_duplicate_differs_in_file_but_is_close_in_phash(self):
        sc = self.sc["cropped_duplicate"]
        items = {i["key"]: i for i in sc["items"]}
        a, b = items["first"], items["cropped"]
        self.assertNotEqual(a["sha256"], b["sha256"])
        self.assertEqual(ham(a["phash"], b["phash"]), 4)
        self.assertEqual(sc["expect"]["phash_distance"], 4)
        self.assertIsNone(b["interpretation"]["fields"]["ticket_id"])
        self.assertEqual(a["interpretation"]["fields"]["qr_payload"], b["interpretation"]["fields"]["qr_payload"])

    def test_cross_sender_duplicate_differs_only_in_sender(self):
        items = {i["key"]: i for i in self.sc["cross_sender_duplicate"]["items"]}
        a, b = items["original"], items["other_sender"]
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertNotEqual(a["sender_id"], b["sender_id"])

    def test_unrelated_evidence_has_unrelated_hashes(self):
        seen = {}
        for name in ("clean_linked_journey", "payment_no_ticket", "inferred_only_link"):
            for it in self.sc[name]["items"]:
                seen.setdefault(it["sha256"], []).append(it["key"])
        self.assertTrue(all(len(v) == 1 for v in seen.values()))

    def test_ambiguous_scenario_lists_both_candidates_and_is_unmatched(self):
        idx = load_into(self.s, only=["ambiguous_two_candidates"])
        rel = self.s.get(idx["ambiguous_two_candidates"]["relationships"][0])
        self.assertEqual(rel["type"], "UNMATCHED")
        self.assertIsNone(rel["to_id"])
        self.assertEqual(len(rel["basis"]), 2)
        keys = idx["ambiguous_two_candidates"]["keys"]
        self.assertEqual({b["candidate"] for b in rel["basis"]}, {keys["payA"]["interp_id"], keys["payB"]["interp_id"]})

    def test_inferred_link_has_no_shared_identifier(self):
        idx = load_into(self.s, only=["inferred_only_link"])
        keys = idx["inferred_only_link"]["keys"]
        pay = self.s.get(keys["pay"]["interp_id"])["fields"]
        tkt = self.s.get(keys["tkt"]["interp_id"])["fields"]
        for ident in ("utr", "order_id", "ticket_id", "qr_payload"):
            self.assertFalse(pay[ident] is not None and pay[ident] == tkt[ident], ident)
        rel = self.s.get(idx["inferred_only_link"]["relationships"][0])
        self.assertEqual(rel["type"], "INFERRED")
        self.assertLess(rel["score"], 1.0)

    def test_manual_link_is_human_and_paired_with_a_decision(self):
        idx = load_into(self.s, only=["manual_link"])
        info = idx["manual_link"]
        rel = self.s.get(info["relationships"][0])
        dec = self.s.get(info["decisions"][0])
        self.assertTrue(rel["created_by"].startswith("coordinator:"))
        self.assertEqual(dec["action"], "manual_link")

    def test_decisions_record_what_the_coordinator_saw(self):
        idx = load_into(self.s, only=["out_of_window_ride"])
        info = idx["out_of_window_ride"]
        dec = self.s.get(info["decisions"][0])
        subj = dec["subject_ref"]
        self.assertEqual(dec["seen_snapshot_hash"], self.s.snapshot_hash([subj]))

    def test_kannada_text_survived(self):
        load_into(self.s, only=["payment_no_ticket"])
        kn = [r for r in self.s.list_records("interpretations") if r["language_detected"] == "kn"]
        self.assertEqual(len(kn), 1)
        self.assertEqual(kn[0]["fields"]["status_text"], "ಬುಕಿಂಗ್ ವಿಫಲವಾಗಿದೆ")

    def test_committed_fixture_file_equals_a_fresh_build(self):
        with open(DEFAULT_PATH, encoding="utf-8") as fh:
            committed = fh.read()
        script = os.path.join(ROOT, "scripts", "build_fixtures.py")
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "scripts")); os.makedirs(os.path.join(tmp, "fixtures"))
        shutil.copy(script, os.path.join(tmp, "scripts", "build_fixtures.py"))
        subprocess.run([sys.executable, os.path.join(tmp, "scripts", "build_fixtures.py")], check=True, capture_output=True)
        with open(os.path.join(tmp, "fixtures", "scenarios.json"), encoding="utf-8") as fh:
            fresh = fh.read()
        self.assertEqual(committed, fresh)


if __name__ == "__main__":
    unittest.main()
