import os
import tempfile
import threading
import unittest

from tests.common import *  # noqa
from pratibimb.canon import GENESIS, compute_hash
from pratibimb.fixtures import load_into
from pratibimb.schema import RECORD_SPECS
from pratibimb.store import record_body, row_to_record


class ChainBase(Base):
    def setUp(self):
        super().setUp()
        self.idx = load_into(self.s)
        self.assertTrue(self.s.verify()["ok"])
        self.conn = self.s.conn

    def link_for(self, record_id):
        return self.conn.execute("SELECT * FROM audit_chain WHERE record_id=?", (record_id,)).fetchone()

    def some_ids(self):
        i = self.s.list_records("interpretations")
        return {"evidence": self.s.list_records("evidence")[4]["evidence_id"],
                "interpretations": i[7]["interp_id"],
                "relationships": self.s.list_records("relationships")[3]["rel_id"],
                "decisions": self.s.list_records("decisions")[0]["dec_id"]}


class TestChainStructure(ChainBase):
    def test_first_link_points_at_genesis_and_links_are_contiguous(self):
        links = self.conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall()
        self.assertEqual(links[0]["prev_hash"], GENESIS)
        for a, b in zip(links, links[1:]):
            self.assertEqual(b["prev_hash"], a["record_hash"])
            self.assertEqual(b["seq"], a["seq"] + 1)
        self.assertEqual(links[-1]["record_hash"], self.s.chain_head())

    def test_every_record_hash_recomputes_independently(self):
        for link in self.conn.execute("SELECT * FROM audit_chain ORDER BY seq"):
            spec = RECORD_SPECS[link["record_type"]]
            row = self.conn.execute(f"SELECT * FROM {spec.table} WHERE {spec.pk}=?", (link["record_id"],)).fetchone()
            rec = row_to_record(spec, row)
            self.assertEqual(compute_hash(record_body(spec, rec), link["prev_hash"]), link["record_hash"])

    def test_one_link_per_record_and_no_orphans(self):
        n = sum(self.s.counts().values())
        self.assertEqual(self.s.chain_length(), n)
        self.assertEqual(self.s.verify()["orphans"], [])

    def test_deterministic_with_fixed_clock_and_ids(self):
        def build():
            s = new_store()
            e = add_ev(s, evidence_id="ev_1")
            add_in(s, e, interp_id="in_1")
            return s.chain_head()
        self.assertEqual(build(), build())

    def test_changing_any_input_changes_the_head(self):
        def build(conf):
            s = new_store()
            e = add_ev(s, evidence_id="ev_1")
            add_in(s, e, interp_id="in_1", type_confidence=conf)
            return s.chain_head()
        self.assertNotEqual(build(0.9), build(0.91))

    def test_reopen_and_continue_chain(self):
        p = os.path.join(tempfile.mkdtemp(), "c.db")
        s1 = new_store(p)
        e = add_ev(s1)
        head = s1.chain_head()
        s1.close()
        s2 = new_store(p)
        self.assertEqual(s2.chain_head(), head)
        add_in(s2, e)
        self.assertTrue(s2.verify(expected_length=2)["ok"])
        s2.close()


class TestTamperDetection(ChainBase):
    """Each test simulates an attacker with raw database access (triggers dropped)."""

    def setUp(self):
        super().setUp()
        self.anchor, self.length = self.s.chain_head(), self.s.chain_length()
        drop_triggers(self.conn)

    def test_edit_any_record_table_is_caught_at_exactly_that_link(self):
        edits = {"evidence": ("sender_id", "'attacker'"),
                 "interpretations": ("type_confidence", "0.01"),
                 "relationships": ("reason", "'rewritten'"),
                 "decisions": ("reason", "'rewritten'")}
        for table, (col, val) in edits.items():
            with self.subTest(table=table):
                s = new_store()
                idx = load_into(s)
                drop_triggers(s.conn)
                spec = RECORD_SPECS[table]
                rid = {"evidence": s.list_records("evidence")[4]["evidence_id"],
                       "interpretations": s.list_records("interpretations")[7]["interp_id"],
                       "relationships": s.list_records("relationships")[3]["rel_id"],
                       "decisions": s.list_records("decisions")[0]["dec_id"]}[table]
                seq = s.conn.execute("SELECT seq FROM audit_chain WHERE record_id=?", (rid,)).fetchone()[0]
                s.conn.execute(f"UPDATE {table} SET {col}={val} WHERE {spec.pk}=?", (rid,))
                res = s.verify()
                self.assertFalse(res["ok"])
                self.assertEqual(res["first_break"]["reason"], "record_modified")
                self.assertEqual(res["first_break"]["seq"], seq)
                self.assertEqual(res["first_break"]["record_id"], rid)
                self.assertEqual(res["checked"], seq - 1)
                s.close()

    def test_edit_inside_json_column(self):
        i = self.some_ids()["interpretations"]
        self.conn.execute(
            "UPDATE interpretations SET fields = json_set(fields, '$.amount', '9999.00') WHERE interp_id=?", (i,))
        self.assertChainBreak("record_modified", self.link_for(i)["seq"])

    def test_edit_and_fix_record_hash_is_caught_by_chain_hash(self):
        i = self.some_ids()["interpretations"]
        self.conn.execute("UPDATE interpretations SET type_confidence=0.01 WHERE interp_id=?", (i,))
        spec = RECORD_SPECS["interpretations"]
        rec = row_to_record(spec, self.conn.execute("SELECT * FROM interpretations WHERE interp_id=?", (i,)).fetchone())
        new = compute_hash(record_body(spec, rec), rec["prev_hash"])
        self.conn.execute("UPDATE interpretations SET record_hash=? WHERE interp_id=?", (new, i))
        self.assertChainBreak("chain_hash_mismatch", self.link_for(i)["seq"])

    def test_edit_and_fix_both_hashes_is_caught_at_the_next_link(self):
        i = self.some_ids()["interpretations"]
        seq = self.link_for(i)["seq"]
        self.conn.execute("UPDATE interpretations SET type_confidence=0.01 WHERE interp_id=?", (i,))
        spec = RECORD_SPECS["interpretations"]
        rec = row_to_record(spec, self.conn.execute("SELECT * FROM interpretations WHERE interp_id=?", (i,)).fetchone())
        new = compute_hash(record_body(spec, rec), rec["prev_hash"])
        self.conn.execute("UPDATE interpretations SET record_hash=? WHERE interp_id=?", (new, i))
        self.conn.execute("UPDATE audit_chain SET record_hash=? WHERE seq=?", (new, seq))
        self.assertChainBreak("chain_prev_mismatch", seq + 1)

    def test_deleting_a_chain_row_is_a_gap(self):
        i = self.some_ids()["interpretations"]
        seq = self.link_for(i)["seq"]
        self.conn.execute("DELETE FROM audit_chain WHERE seq=?", (seq,))
        self.assertChainBreak("chain_gap", seq)

    def test_deleting_a_record_row(self):
        d = self.some_ids()["decisions"]
        seq = self.link_for(d)["seq"]
        self.conn.execute("DELETE FROM decisions WHERE dec_id=?", (d,))
        self.assertChainBreak("record_missing", seq)

    def test_record_inserted_around_the_store_is_an_orphan(self):
        spec = RECORD_SPECS["decisions"]
        src = self.conn.execute("SELECT * FROM decisions LIMIT 1").fetchone()
        cols = [c for c in src.keys()]
        vals = {c: src[c] for c in cols}
        vals["dec_id"], vals["record_hash"] = "dc_forged000001", "f" * 64
        self.conn.execute(f"INSERT INTO decisions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                          [vals[c] for c in cols])
        res = self.assertChainBreak("record_not_in_chain")
        self.assertEqual(res["first_break"]["record_id"], "dc_forged000001")
        self.assertEqual(res["orphans"], [{"record_type": "decisions", "record_id": "dc_forged000001"}])

    def test_swapping_two_chain_rows_is_caught(self):
        a, b = 10, 11
        la = self.conn.execute("SELECT record_hash FROM audit_chain WHERE seq=?", (a,)).fetchone()[0]
        lb = self.conn.execute("SELECT record_hash FROM audit_chain WHERE seq=?", (b,)).fetchone()[0]
        self.conn.execute("UPDATE audit_chain SET record_hash='tmp' WHERE seq=?", (a,))
        self.conn.execute("UPDATE audit_chain SET record_hash=? WHERE seq=?", (la, b))
        self.conn.execute("UPDATE audit_chain SET record_hash=? WHERE seq=?", (lb, a))
        res = self.s.verify()
        self.assertFalse(res["ok"])
        self.assertEqual(res["first_break"]["seq"], a)

    def test_tail_truncation_needs_the_anchor(self):
        last = self.conn.execute("SELECT * FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
        spec = RECORD_SPECS[last["record_type"]]
        self.conn.execute(f"DELETE FROM audit_chain WHERE seq=?", (last["seq"],))
        self.conn.execute(f"DELETE FROM {spec.table} WHERE {spec.pk}=?", (last["record_id"],))
        self.assertTrue(self.s.verify()["ok"], "without an anchor, a clean tail cut is invisible (documented limit)")
        self.assertChainBreak("length_mismatch", expected_length=self.length)
        self.assertChainBreak("head_mismatch", expected_head=self.anchor)

    def test_write_after_tail_truncation_exposes_a_gap(self):
        last = self.conn.execute("SELECT * FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
        spec = RECORD_SPECS[last["record_type"]]
        self.conn.execute("DELETE FROM audit_chain WHERE seq=?", (last["seq"],))
        self.conn.execute(f"DELETE FROM {spec.table} WHERE {spec.pk}=?", (last["record_id"],))
        add_ev(self.s, sha256=SHA_B)
        self.assertChainBreak("chain_gap", last["seq"])

    def test_full_rewrite_passes_verify_but_not_the_anchor(self):
        i = self.some_ids()["interpretations"]
        self.conn.execute("UPDATE interpretations SET type_confidence=0.01 WHERE interp_id=?", (i,))
        prev = GENESIS
        for link in self.conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall():
            spec = RECORD_SPECS[link["record_type"]]
            rec = row_to_record(spec, self.conn.execute(
                f"SELECT * FROM {spec.table} WHERE {spec.pk}=?", (link["record_id"],)).fetchone())
            h = compute_hash(record_body(spec, rec), prev)
            self.conn.execute(f"UPDATE {spec.table} SET prev_hash=?, record_hash=? WHERE {spec.pk}=?",
                              (prev, h, link["record_id"]))
            self.conn.execute("UPDATE audit_chain SET prev_hash=?, record_hash=? WHERE seq=?", (prev, h, link["seq"]))
            prev = h
        self.assertTrue(self.s.verify()["ok"])
        self.assertChainBreak("head_mismatch", expected_head=self.anchor)

    def test_first_break_is_reported_when_there_are_several(self):
        ids = self.some_ids()
        self.conn.execute("UPDATE decisions SET reason='x' WHERE dec_id=?", (ids["decisions"],))
        self.conn.execute("UPDATE evidence SET sender_id='x' WHERE evidence_id=?", (ids["evidence"],))
        res = self.s.verify()
        self.assertEqual(res["first_break"]["seq"], min(self.link_for(ids["decisions"])["seq"],
                                                       self.link_for(ids["evidence"])["seq"]))


class TestConcurrency(Base):
    def test_parallel_writers_keep_one_valid_chain(self):
        ev = add_ev(self.s)
        errors = []

        def work(n):
            try:
                for k in range(15):
                    e = add_ev(self.s, sender_id=f"s{n}", sha256=f"{n:02x}{k:02x}".ljust(64, "0"))
                    add_in(self.s, e)
            except Exception as ex:                       # pragma: no cover
                errors.append(ex)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(self.s.counts()["evidence"], 1 + 8 * 15)
        self.assertEqual(self.s.counts()["interpretations"], 8 * 15)
        res = self.s.verify(expected_length=1 + 8 * 15 * 2)
        self.assertTrue(res["ok"], res)

    def test_two_processes_style_writers_on_a_file_db(self):
        p = os.path.join(tempfile.mkdtemp(), "mp.db")
        s1, s2 = new_store(p), new_store(p)
        for k in range(10):
            add_ev(s1, sha256=f"{k:02x}".ljust(64, "1"))
            add_ev(s2, sha256=f"{k:02x}".ljust(64, "2"))
        self.assertTrue(s1.verify(expected_length=20)["ok"])
        self.assertTrue(s2.verify(expected_length=20)["ok"])
        s1.close(); s2.close()


if __name__ == "__main__":
    unittest.main()
