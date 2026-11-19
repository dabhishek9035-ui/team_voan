import re
import sqlite3
import unittest

from tests.common import *  # noqa
from pratibimb import Store
from pratibimb.fixtures import load_into
from pratibimb.schema import APPEND_ONLY_TABLES


class TestAppendOnly(Base):
    def setUp(self):
        super().setUp()
        load_into(self.s)
        self.s.log_access("coordinator:c_priya", "view_raw_image", "ev_x", "checking a suspected duplicate")
        self.s.conn.execute(
            "INSERT INTO cases VALUES ('cr1','CASE-1','trip_demo','payment_seen','[]','2026-11-19T10:00:00Z',NULL,'2026-11-19T10:00:00Z',NULL)")
        self.s.add_join_code("trip_demo", "c_priya")
        self.s.add_assertion("trip_demo", "s_asha")
        self.s.add_challenge("in_x", "trip_demo", "debit", "bank_sms", "no_second_source", "m", "2026-11-21T00:00:00Z")

    def first_pk(self, table):
        row = self.s.conn.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
        return row.keys()[0], row[0], row.keys()[1]

    def test_every_table_refuses_update(self):
        for t in APPEND_ONLY_TABLES:
            with self.subTest(table=t):
                pk, val, col = self.first_pk(t)
                with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                    self.s.conn.execute(f"UPDATE {t} SET {col} = {col} WHERE {pk} = ?", (val,))

    def test_every_table_refuses_delete(self):
        for t in APPEND_ONLY_TABLES:
            with self.subTest(table=t):
                pk, val, _ = self.first_pk(t)
                with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                    self.s.conn.execute(f"DELETE FROM {t} WHERE {pk} = ?", (val,))

    def test_insert_or_replace_is_also_refused(self):
        row = self.s.conn.execute("SELECT * FROM evidence LIMIT 1").fetchone()
        cols = row.keys()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
            self.s.conn.execute(
                f"INSERT OR REPLACE INTO evidence ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(row))

    def test_refused_raw_writes_leave_chain_intact(self):
        try:
            self.s.conn.execute("DELETE FROM decisions")
        except sqlite3.DatabaseError:
            pass
        self.assertTrue(self.s.verify()["ok"])

    def test_store_has_no_mutating_methods(self):
        bad = [n for n in dir(Store) if re.match(r"^(update|delete|remove|set|edit|modify|overwrite|replace)", n)]
        self.assertEqual(bad, [])

    def test_no_update_or_delete_sql_in_store_source(self):
        import inspect
        import pratibimb.store as mod
        src = inspect.getsource(mod)
        self.assertNotRegex(src, r"(?i)\bUPDATE\s+\w+\s+SET\b")
        self.assertNotRegex(src, r"(?i)\bDELETE\s+FROM\b")
        self.assertNotRegex(src, r"(?i)INSERT\s+OR\s+REPLACE")


if __name__ == "__main__":
    unittest.main()
