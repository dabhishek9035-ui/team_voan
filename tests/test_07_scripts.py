import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.common import ROOT
from pratibimb import Store


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def anchor_of(out):
    return [l for l in out.splitlines() if l.startswith("anchor")][0].split("=")[1]


class TestScripts(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "t.db")
        r = run("scripts/load_fixtures.py", "--db", self.db)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.anchor = anchor_of(r.stdout)

    def verify(self, *extra):
        r = run("scripts/verify_chain.py", "--db", self.db, *extra)
        return r.returncode, json.loads(r.stdout)

    def test_load_refuses_to_overwrite_without_force(self):
        r = run("scripts/load_fixtures.py", "--db", self.db)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--force", r.stderr)
        self.assertEqual(run("scripts/load_fixtures.py", "--db", self.db, "--force").returncode, 0)

    def test_verify_clean(self):
        code, res = self.verify("--anchor", self.anchor, "--length", "53")
        self.assertEqual((code, res["ok"], res["checked"]), (0, True, 53))

    def test_verify_missing_db(self):
        self.assertNotEqual(run("scripts/verify_chain.py", "--db", self.db + ".nope").returncode, 0)

    def test_tamper_edit_is_detected_at_the_right_record(self):
        s = Store(self.db)
        target = s.list_records("relationships")[2]
        r = run("scripts/tamper.py", "--db", self.db, "--record-id", target["rel_id"], "--column", "reason", "--value", "edited")
        self.assertEqual(r.returncode, 0, r.stderr)
        code, res = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(res["first_break"]["reason"], "record_modified")
        self.assertEqual(res["first_break"]["record_id"], target["rel_id"])

    def test_tamper_json_column(self):
        s = Store(self.db)
        target = s.list_records("relationships")[0]
        r = run("scripts/tamper.py", "--db", self.db, "--record-id", target["rel_id"], "--column", "basis", "--value", '["forged"]')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.verify()[0], 1)

    def test_tamper_delete_chain_row(self):
        s = Store(self.db)
        target = s.list_records("decisions")[0]["dec_id"]
        self.assertEqual(run("scripts/tamper.py", "--db", self.db, "--record-id", target, "--mode", "delete-chain-row").returncode, 0)
        code, res = self.verify()
        self.assertEqual((code, res["first_break"]["reason"]), (1, "chain_gap"))

    def test_tamper_rewrite_fools_verify_but_not_anchor(self):
        s = Store(self.db)
        target = s.list_records("interpretations")[3]["interp_id"]
        r = run("scripts/tamper.py", "--db", self.db, "--record-id", target, "--column", "type_confidence",
                "--value", "0.01", "--mode", "rewrite")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.verify()[0], 0)
        code, res = self.verify("--anchor", self.anchor)
        self.assertEqual((code, res["first_break"]["reason"]), (1, "head_mismatch"))

    def test_tamper_rejects_bad_input(self):
        s = Store(self.db)
        target = s.list_records("evidence")[0]["evidence_id"]
        for args in (["--record-id", "zz_1", "--column", "x", "--value", "1"],
                     ["--record-id", "ev_missing", "--column", "sender_id", "--value", "1"],
                     ["--record-id", target, "--column", "record_hash", "--value", "1"],
                     ["--record-id", target, "--column", "sender_id; DROP TABLE evidence", "--value", "1"],
                     ["--record-id", target]):
            with self.subTest(args=args):
                self.assertNotEqual(run("scripts/tamper.py", "--db", self.db, *args).returncode, 0)
        self.assertEqual(self.verify()[0], 0, "rejected tamper attempts must not have changed anything")

    def test_demo_script_passes(self):
        r = run("scripts/demo_day1.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ALL CHECKS PASSED", r.stdout)


if __name__ == "__main__":
    unittest.main()
