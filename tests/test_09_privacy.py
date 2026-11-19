import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tests.common import Base, add_ev, add_in
from pratibimb import privacy as pv
from pratibimb.config import load_config
from pratibimb.errors import NotFoundError, ValidationError

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


class TestMasking(unittest.TestCase):
    def test_masks(self):
        self.assertEqual(pv.mask_name("Meera Kumar"), "M***a K***r")
        self.assertEqual(pv.mask_id("UTR123456789"), "********6789")
        self.assertEqual(pv.mask_id("ab"), "**")
        self.assertTrue(pv.mask_payload("NMMR-SECRET-PAYLOAD").endswith("(hidden)"))
        self.assertNotIn("98450", pv.hide_phones("call 98450 12345 now"))
        self.assertNotIn("9845012345", pv.hide_phones("+91 9845012345"))

    def test_mask_fields_keeps_non_sensitive_and_nulls(self):
        f = {"amount": "40.00", "utr": "UTR123456789", "payer_name_masked": "Meera K", "ticket_id": None,
             "status_text": "Paid by 9845012345"}
        m = pv.mask_fields(f)
        self.assertEqual(m["amount"], "40.00")
        self.assertEqual(m["utr"], "********6789")
        self.assertIsNone(m["ticket_id"])
        self.assertNotIn("9845012345", m["status_text"])
        self.assertEqual(f["utr"], "UTR123456789", "input must not be mutated")


class TestAccess(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.cfg = load_config({"blob_dir": self.tmp})
        with open(os.path.join(self.tmp, "a.png"), "wb") as fh:
            fh.write(b"img")
        self.ev = add_ev(self.s, file_ref="a.png")
        self.ip = add_in(self.s, self.ev, fields={"utr": "UTR123456789"}, field_confidence={"utr": 0.9},
                         field_source={"utr": "sarvam_extract"})

    def test_views_hide_images_and_mask(self):
        e = pv.view_evidence(self.s.get(self.ev))
        self.assertIsNone(e["file_ref"])
        self.assertTrue(e["has_raw_image"])
        i = pv.view_interpretation(self.s.get(self.ip))
        self.assertEqual(i["fields"]["utr"], "********6789")

    def test_raw_image_needs_coordinator_and_reason_and_is_logged(self):
        for actor, reason in (("system:x", "why"), ("coordinator:c", " ")):
            with self.assertRaises(ValidationError):
                pv.request_raw_image(self.s, self.ev, actor, reason, self.cfg)
        p = pv.request_raw_image(self.s, self.ev, "coordinator:c", "dispute", self.cfg)
        self.assertTrue(p.endswith("a.png"))
        acts = [(e["action"], e["actor"], e["reason"]) for e in self.s.access_log()]
        self.assertIn(("raw_image_served", "coordinator:c", "dispute"), acts)

    def test_path_traversal_blocked(self):
        ev = add_ev(self.s, sha256="d" * 64, file_ref="../../etc/passwd")
        with self.assertRaises(ValidationError):
            pv.request_raw_image(self.s, ev, "coordinator:c", "x", self.cfg)

    def test_reveal_needs_a_decision(self):
        with self.assertRaises(ValidationError):
            pv.reveal_fields(self.s, self.ip, "coordinator:c", "need full utr")
        self.s.add_decision(self.ip, "proof_requested", "coordinator:c", "check", self.s.snapshot_hash([self.ip]))
        self.assertEqual(pv.reveal_fields(self.s, self.ip, "coordinator:c", "need full utr")["utr"], "UTR123456789")
        self.assertEqual(self.s.access_log()[-1]["action"], "reveal_full_fields")

    def test_retention_deletes_old_image_and_logs_it(self):
        old = NOW + timedelta(days=self.cfg["raw_image_retention_days"] + 1)
        self.assertEqual(pv.retention_sweep(self.s, self.cfg, NOW), [])
        dry = pv.retention_sweep(self.s, self.cfg, old, dry_run=True)
        self.assertEqual(len(dry), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "a.png")))
        out = pv.retention_sweep(self.s, self.cfg, old)
        self.assertEqual(out[0]["why"], "retention period elapsed")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "a.png")))
        self.assertEqual(pv.retention_sweep(self.s, self.cfg, old), [], "idempotent")
        with self.assertRaises(NotFoundError):
            pv.request_raw_image(self.s, self.ev, "coordinator:c", "later", self.cfg)
        self.assertTrue(self.s.verify()["ok"])
        self.assertEqual(self.s.get(self.ip)["fields"]["utr"], "UTR123456789", "fields are retained")


if __name__ == "__main__":
    unittest.main()
