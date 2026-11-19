#!/usr/bin/env python3
"""Verify the audit chain of a database. Exit code 0 = intact, 1 = broken."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pratibimb import Store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
ap.add_argument("--anchor", help="expected head hash, stored outside the database")
ap.add_argument("--length", type=int, help="expected number of chain links")
a = ap.parse_args()
if not os.path.exists(a.db):
    sys.exit(f"no such database: {a.db}")
res = Store(a.db).verify(expected_head=a.anchor, expected_length=a.length)
print(json.dumps(res, indent=2))
sys.exit(0 if res["ok"] else 1)
