import hashlib
import sqlite3
import unittest

from tests.common import *  # noqa
from pratibimb.canon import GENESIS, canonical_json, compute_hash
from pratibimb.schema import APPEND_ONLY_TABLES, RECORD_SPECS, trigger_names


class TestHashing(unittest.TestCase):
    def test_canonical_json_is_sorted_compact_unicode(self):
        self.assertEqual(canonical_json({"b": 1, "a": "ಕ"}), '{"a":"ಕ","b":1}')

    def test_known_answer_pins_the_format(self):
        expected = hashlib.sha256(('{"a":"ಕ","b":1}' + "0" * 64).encode("utf-8")).hexdigest()
        self.assertEqual(compute_hash({"b": 1, "a": "ಕ"}, GENESIS), expected)

    def test_key_order_does_not_change_hash(self):
        self.assertEqual(compute_hash({"a": 1, "b": 2}, GENESIS), compute_hash({"b": 2, "a": 1}, GENESIS))

    def test_prev_hash_changes_hash(self):
        self.assertNotEqual(compute_hash({"a": 1}, GENESIS), compute_hash({"a": 1}, "1" * 64))

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            canonical_json({"x": float("nan")})


class TestSchema(Base):
    def test_all_tables_exist(self):
        names = {r[0] for r in self.s.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in APPEND_ONLY_TABLES:
            self.assertIn(t, names)

    def test_spec_columns_match_database_columns(self):
        for t, spec in RECORD_SPECS.items():
            db_cols = [r["name"] for r in self.s.conn.execute(f"PRAGMA table_info({t})")]
            self.assertEqual(db_cols, [spec.pk, *spec.columns, "prev_hash", "record_hash"], t)

    def test_one_update_and_one_delete_trigger_per_table(self):
        names = {r[0] for r in self.s.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(names, set(trigger_names()))
        self.assertEqual(len(names), 2 * len(APPEND_ONLY_TABLES))

    def test_schema_version_recorded(self):
        v = self.s.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        self.assertEqual(v, "1.0")

    def test_reopening_a_database_is_idempotent(self):
        import os, tempfile
        p = os.path.join(tempfile.mkdtemp(), "x.db")
        s1 = new_store(p)
        ev = add_ev(s1)
        s1.close()
        s2 = new_store(p)
        self.assertEqual(s2.get(ev)["sender_id"], "s1")
        self.assertEqual(s2.counts()["evidence"], 1)
        self.assertTrue(s2.verify()["ok"])
        s2.close()


if __name__ == "__main__":
    unittest.main()
