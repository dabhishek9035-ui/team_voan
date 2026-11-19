import unittest

from tests.common import *  # noqa
from pratibimb import SupersedeError


class TestSupersedes(Base):
    def test_chain_of_corrections_and_history(self):
        e = add_ev(self.s)
        a = add_in(self.s, e, model_version="v1")
        b = add_in(self.s, e, model_version="v2", supersedes=a)
        c = add_in(self.s, e, model_version="v3", supersedes=b)
        for start in (a, b, c):
            self.assertEqual([r["interp_id"] for r in self.s.history(start)], [a, b, c])
        self.assertEqual([self.s.is_current(x) for x in (a, b, c)], [False, False, True])
        self.assertEqual([r["interp_id"] for r in self.s.list_records("interpretations")], [c])
        self.assertEqual(len(self.s.list_records("interpretations", current_only=False)), 3)
        self.assertTrue(self.s.verify()["ok"])

    def test_old_record_is_never_altered_by_a_correction(self):
        e = add_ev(self.s)
        a = add_in(self.s, e)
        before = self.s.get(a)
        add_in(self.s, e, supersedes=a, type_confidence=0.1)
        self.assertEqual(self.s.get(a), before)

    def test_cannot_branch(self):
        e = add_ev(self.s)
        a = add_in(self.s, e)
        add_in(self.s, e, supersedes=a)
        n = self.s.chain_length()
        with self.assertRaisesRegex(SupersedeError, "already superseded"):
            add_in(self.s, e, supersedes=a)
        self.assertEqual(self.s.chain_length(), n)

    def test_unknown_and_wrong_table_targets(self):
        e = add_ev(self.s)
        a = add_in(self.s, e)
        with self.assertRaises(SupersedeError):
            add_in(self.s, e, supersedes="in_doesnotexist")
        with self.assertRaises(SupersedeError):
            add_in(self.s, e, supersedes=e)                 # an evidence id given to an interpretation
        with self.assertRaises(SupersedeError):
            add_ev(self.s, supersedes=a)                    # an interpretation id given to evidence

    def test_reextraction_must_stay_on_the_same_evidence(self):
        e1, e2 = add_ev(self.s), add_ev(self.s, sha256=SHA_B)
        a = add_in(self.s, e1)
        with self.assertRaisesRegex(SupersedeError, "same evidence"):
            add_in(self.s, e2, supersedes=a)

    def test_evidence_relationship_decision_corrections(self):
        e1 = add_ev(self.s)
        e1b = add_ev(self.s, supersedes=e1, status="quarantined")
        self.assertTrue(self.s.is_current(e1b))
        e2 = add_ev(self.s, sha256=SHA_B)
        i1, i2 = add_in(self.s, e1), add_in(self.s, e2)
        r1 = self.s.add_relationship(i1, i2, "INFERRED", ["amount"], 0.5, "amount equal", "system:linker")
        r2 = self.s.add_relationship(i1, None, "UNMATCHED", [], None, "ambiguous on review", "system:linker", supersedes=r1)
        snap = self.s.snapshot_hash([i1])
        d1 = self.s.add_decision(i1, "proof_requested", "coordinator:c1", "need bank sms", snap)
        d2 = self.s.add_decision(i1, "approved", "coordinator:c1", "sms received", snap, supersedes=d1)
        self.assertEqual([r["rel_id"] for r in self.s.list_records("relationships")], [r2])
        self.assertEqual([r["dec_id"] for r in self.s.list_records("decisions", subject_ref=i1)], [d2])
        self.assertTrue(self.s.verify()["ok"])

    def test_list_filters_validated(self):
        from pratibimb import ValidationError
        with self.assertRaises(ValidationError):
            self.s.list_records("interpretations", evil="1; DROP TABLE evidence")
        with self.assertRaises(ValidationError):
            self.s.list_records("trips")
        self.assertEqual(self.s.counts()["evidence"], 0)


if __name__ == "__main__":
    unittest.main()
