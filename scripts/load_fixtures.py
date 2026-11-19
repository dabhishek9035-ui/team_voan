#!/usr/bin/env python3
"""Create a fresh database seeded with the synthetic fixtures. Prints the chain head: save it as the anchor."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pratibimb import Store  # noqa: E402
from pratibimb.fixtures import load_into  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
ap.add_argument("--force", action="store_true", help="delete an existing db file first")
a = ap.parse_args()
if os.path.exists(a.db):
    if not a.force:
        sys.exit(f"{a.db} exists; pass --force to replace it")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(a.db + suffix):
            os.remove(a.db + suffix)
s = Store(a.db)
idx = load_into(s)
print(f"seeded {a.db}: {s.counts()}")
print(f"chain_length={s.chain_length()}")
print(f"anchor (head hash)={s.chain_head()}")
