import unittest

from tests.common import *  # noqa
from pratibimb import NotFoundError, SupersedeError, ValidationError
from pratibimb.enums import FIELD_KEYS


class TestEvidenceValidation(Base):
    def bad(self, **kw):
        n = self.s.chain_length()
        with self.assertRaises(ValidationError, msg=str(kw)):
            add_ev(self.s, **kw)
        self.assertEqual(self.s.chain_length(), n, "a rejected write must leave nothing behind")

    def test_rejections(self):
        self.bad(sha256="abc")
        self.bad(sha256="A" * 64)             # uppercase
        self.bad(sha256="g" * 64)             # not hex
        self.bad(phash="xyz")
        self.bad(sender_id="")
        self.bad(sender_id=None)
        self.bad(channel="  ")
        self.bad(received_at="yesterday")
        self.bad(received_at="2026-11-18T09:00:00")     # naive
        self.bad(status="deleted")

    def test_unknown_trip_rejected(self):
        with self.assertRaises(NotFoundError):
            add_ev(self.s, trip_id="trip_nope")

    def test_accepts_z_and_offset_timestamps(self):
        add_ev(self.s, received_at="2026-11-18T03:30:00Z")
        add_ev(self.s, received_at="2026-11-18T09:00:00+05:30")

    def test_id_prefix_enforced_and_duplicate_id_rejected(self):
        with self.assertRaises(ValidationError):
            add_ev(self.s, evidence_id="xx_1")
        add_ev(self.s, evidence_id="ev_fixed1")
        n = self.s.chain_length()
        with self.assertRaises(ValidationError):
            add_ev(self.s, evidence_id="ev_fixed1")
        self.assertEqual(self.s.chain_length(), n)
        add_ev(self.s)  # store still usable: no half-open transaction left behind
        self.assertTrue(self.s.verify()["ok"])


class TestInterpretationValidation(Base):
    def setUp(self):
        super().setUp()
        self.ev = add_ev(self.s)

    def bad(self, exc=ValidationError, **kw):
        n = self.s.chain_length()
        with self.assertRaises(exc, msg=str(kw)):
            add_in(self.s, self.ev, **kw)
        self.assertEqual(self.s.chain_length(), n)

    def test_unknown_evidence(self):
        with self.assertRaises(NotFoundError):
            add_in(self.s, "ev_missing")

    def test_type_and_confidence(self):
        self.bad(screenshot_type="PHOTO")
        self.bad(type_confidence=1.5)
        self.bad(type_confidence=-0.1)
        self.bad(type_confidence="high")
        self.bad(type_confidence=True)
        self.bad(type_confidence=float("nan"))

    def test_unknown_field_key_rejected(self):
        self.bad(fields={"amount": "1", "colour": "red"}, field_confidence={"amount": 0.9, "colour": 0.9})

    def test_null_must_have_zero_confidence(self):
        self.bad(fields={"amount": None}, field_confidence={"amount": 0.7}, field_source={})

    def test_value_needs_confidence_source_and_nonzero(self):
        self.bad(fields={"amount": "1"}, field_confidence={})
        self.bad(fields={"amount": "1"}, field_confidence={"amount": 0.0})
        self.bad(field_source={})
        self.bad(field_source={"amount": "gut_feeling"})

    def test_bad_value_types(self):
        for val in ({"a": 1}, [1], True, float("inf")):
            self.bad(fields={"amount": val})

    def test_normalised_to_all_sixteen_keys(self):
        r = self.s.get(add_in(self.s, self.ev))
        self.assertEqual(set(r["fields"]), set(FIELD_KEYS))
        self.assertEqual(set(r["field_confidence"]), set(FIELD_KEYS))
        self.assertIsNone(r["fields"]["utr"])
        self.assertEqual(r["field_confidence"]["utr"], 0.0)
        self.assertEqual(r["fields"]["amount"], "40.00")

    def test_numbers_allowed_in_fields(self):
        r = self.s.get(add_in(self.s, self.ev, fields={"amount": 40.5, "fare": 40},
                              field_confidence={"amount": 0.9, "fare": 0.9},
                              field_source={"amount": "qr_decoder", "fare": "sarvam_digitise"}))
        self.assertEqual(r["fields"]["fare"], 40)

    def test_int_confidence_hashes_stably(self):
        # int 1 is stored as REAL 1.0; if it were hashed as 1 the chain would break on re-read
        add_in(self.s, self.ev, type_confidence=1)
        add_in(self.s, self.ev, type_confidence=0, fields={}, field_confidence={}, field_source={})
        self.assertTrue(self.s.verify()["ok"])

    def test_kannada_round_trips_and_verifies(self):
        txt = "ಬುಕಿಂಗ್ ವಿಫಲವಾಗಿದೆ"
        i = add_in(self.s, self.ev, screenshot_type="BOT_ERROR", fields={"status_text": txt},
                   field_confidence={"status_text": 0.8}, field_source={"status_text": "sarvam_extract"},
                   language_detected="kn")
        self.assertEqual(self.s.get(i)["fields"]["status_text"], txt)
        self.assertTrue(self.s.verify()["ok"])

    def test_model_upgrade_is_a_new_interpretation(self):
        a = add_in(self.s, self.ev, model_version="v1")
        b = add_in(self.s, self.ev, model_version="v2", supersedes=a)
        cur = self.s.interpretations_for(self.ev)
        self.assertEqual([r["interp_id"] for r in cur], [b])
        self.assertEqual(len(self.s.interpretations_for(self.ev, current_only=False)), 2)


class TestRelationshipValidation(Base):
    def setUp(self):
        super().setUp()
        e1, e2 = add_ev(self.s), add_ev(self.s, sha256=SHA_B)
        self.a, self.b = add_in(self.s, e1), add_in(self.s, e2)

    def rel(self, **kw):
        args = dict(from_id=self.a, to_id=self.b, type="EXACT", basis=["utr"], score=0.9,
                    reason="same UTR", created_by="system:linker")
        args.update(kw)
        return self.s.add_relationship(**args)

    def bad(self, exc=ValidationError, **kw):
        n = self.s.chain_length()
        with self.assertRaises(exc, msg=str(kw)):
            self.rel(**kw)
        self.assertEqual(self.s.chain_length(), n)

    def test_valid_each_type(self):
        self.rel()
        self.rel(type="INFERRED", basis=["amount", "timestamp_window"], score=0.6)
        self.rel(type="MANUAL", basis=["coordinator_judgement"], score=None, created_by="coordinator:c1")
        self.rel(type="UNMATCHED", to_id=None, basis=[{"candidate": self.b}], score=None)
        self.assertTrue(self.s.verify()["ok"])

    def test_exact_and_inferred_need_basis_score_and_target(self):
        self.bad(basis=[])
        self.bad(score=None)
        self.bad(to_id=None)
        self.bad(type="INFERRED", basis=[])

    def test_machine_cannot_create_manual_and_human_cannot_create_exact(self):
        self.bad(type="MANUAL", created_by="system:linker")
        self.bad(type="EXACT", created_by="coordinator:c1")

    def test_other_rejections(self):
        self.bad(type="PROBABLE")
        self.bad(score=1.2)
        self.bad(reason="")
        self.bad(to_id=self.a)                               # self-link
        self.bad(from_id="rl_abc")                           # relationships can't link relationships
        self.bad(basis=[1])

    def test_unknown_endpoint(self):
        self.bad(NotFoundError, to_id="in_doesnotexist")
        self.bad(NotFoundError, from_id="ev_doesnotexist")


class TestDecisionValidation(Base):
    def setUp(self):
        super().setUp()
        self.ev = add_ev(self.s)
        self.i = add_in(self.s, self.ev)

    def dec(self, **kw):
        args = dict(subject_ref=self.i, action="approved", decided_by="coordinator:c1", reason="looks consistent",
                    seen_snapshot_hash=self.s.snapshot_hash([self.i]))
        args.update(kw)
        return self.s.add_decision(**args)

    def test_valid(self):
        d = self.dec()
        self.assertEqual(self.s.get(d)["action"], "approved")
        self.assertEqual(self.s.get(d)["seen_snapshot_hash"], self.s.snapshot_hash([self.i]))

    def test_rejections(self):
        for kw, exc in [({"decided_by": "system:auto"}, ValidationError),
                        ({"decided_by": "c1"}, ValidationError),
                        ({"action": "auto_approved"}, ValidationError),
                        ({"reason": ""}, ValidationError),
                        ({"seen_snapshot_hash": "short"}, ValidationError),
                        ({"subject_ref": "in_nope"}, NotFoundError),
                        ({"subject_ref": "garbage"}, ValidationError)]:
            with self.subTest(kw=kw):
                n = self.s.chain_length()
                with self.assertRaises(exc):
                    self.dec(**kw)
                self.assertEqual(self.s.chain_length(), n)

    def test_decision_can_target_evidence_relationship_or_decision(self):
        e2 = add_ev(self.s, sha256=SHA_B)
        i2 = add_in(self.s, e2)
        r = self.s.add_relationship(self.i, i2, "EXACT", ["utr"], 0.9, "same utr", "system:linker")
        d1 = self.dec(subject_ref=self.ev)
        d2 = self.dec(subject_ref=r)
        d3 = self.dec(subject_ref=d1)
        self.assertTrue(self.s.verify()["ok"])

    def test_snapshot_hash_changes_when_subject_is_corrected(self):
        before = self.s.snapshot_hash([self.i])
        new = add_in(self.s, self.ev, supersedes=self.i, type_confidence=0.5)
        self.assertNotEqual(before, self.s.snapshot_hash([new]))
        self.assertEqual(before, self.s.snapshot_hash([self.i]))   # old record's hash never changes


class TestAccessLog(Base):
    def test_logged_and_validated(self):
        self.s.log_access("coordinator:c1", "view_raw_image", "ev_1", "suspected duplicate")
        log = self.s.access_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["reason"], "suspected duplicate")
        with self.assertRaises(ValidationError):
            self.s.log_access("coordinator:c1", "view_raw_image", "ev_1", "")


class TestTripsAndTravellers(Base):
    def test_trip_and_traveller(self):
        t = self.s.add_trip("Offsite", "c1")
        self.s.add_traveller(t, "s1", "Asha")
        with self.assertRaises(ValidationError):
            self.s.add_traveller(t, "s1")            # same sender twice
        with self.assertRaises(NotFoundError):
            self.s.add_traveller("trip_x", "s2")
        with self.assertRaises(ValidationError):
            self.s.add_trip("Offsite", "c1", trip_id=t)
        add_ev(self.s, trip_id=t)


if __name__ == "__main__":
    unittest.main()


class TestAtomicity(Base):
    def test_failure_after_the_record_insert_rolls_the_record_back(self):
        """Force the chain insert (the second statement) to fail and check the record row vanishes."""
        drop_triggers(self.s.conn)
        self.s.conn.execute(
            "INSERT INTO audit_chain (record_type, record_id, prev_hash, record_hash, created_at) "
            "VALUES ('evidence','ev_collide','x','y','2026-11-19T10:00:00Z')")
        with self.assertRaises(ValidationError):
            add_ev(self.s, evidence_id="ev_collide")
        self.assertEqual(self.s.counts()["evidence"], 0, "half-written record must be rolled back")
        self.assertEqual(self.s.conn.execute("SELECT COUNT(*) FROM audit_chain").fetchone()[0], 1)
        add_ev(self.s)  # and the connection is not stuck in a transaction
