import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from pratibimb import Store  # noqa: E402
from pratibimb.schema import trigger_names  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64
TS = "2026-11-18T09:00:00+05:30"


def fixed_clock():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-11-19T10:00:00.{n['i']:03d}Z"
    return clock


def new_store(path=":memory:"):
    return Store(path, clock=fixed_clock())


def add_ev(s, **kw):
    args = dict(sender_id="s1", channel="telegram", received_at=TS, sha256=SHA_A, phash="ab" * 8)
    args.update(kw)
    return s.add_evidence(**args)


def add_in(s, ev, **kw):
    args = dict(evidence_id=ev, producer="test", model_version="t1", screenshot_type="UPI_SUCCESS",
                type_confidence=0.9, fields={"amount": "40.00"}, field_confidence={"amount": 0.9},
                field_source={"amount": "sarvam_extract"})
    args.update(kw)
    return s.add_interpretation(**args)


def drop_triggers(conn):
    for n in trigger_names():
        conn.execute(f"DROP TRIGGER IF EXISTS {n}")


class Base(unittest.TestCase):
    def setUp(self):
        self.s = new_store()

    def tearDown(self):
        self.s.close()

    def assertChainBreak(self, reason, seq="__any__", **verify_kw):
        res = self.s.verify(**verify_kw)
        self.assertFalse(res["ok"], f"expected a break ({reason}) but chain verified")
        self.assertEqual(res["first_break"]["reason"], reason, res["first_break"])
        if seq != "__any__":
            self.assertEqual(res["first_break"]["seq"], seq, res["first_break"])
        return res
