#!/usr/bin/env python3
"""TAMPER DEMO for Member C's live demo. Deliberately edits a past row, bypassing the store.

The chain gives tamper EVIDENCE, not tamper PREVENTION, and it is not a blockchain.
To simulate an attacker with raw database access this script first DROPS the append-only
triggers, which is exactly why the real protection is verify(), not the triggers.

Modes
  edit        change one column of one record; leaves all hashes alone      -> record_modified at that link
  rewrite     change the column AND recompute every hash from there on      -> verify passes; only an
              external --anchor (head hash saved before the attack) catches it
  delete-chain-row  delete the chain row for the record                     -> chain_gap
Examples
  python3 scripts/tamper.py --db demo.db --record-id in_xxx --column type_confidence --value 0.01
  python3 scripts/tamper.py --db demo.db --record-id in_xxx --column type_confidence --value 0.01 --mode rewrite
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pratibimb.canon import GENESIS, compute_hash  # noqa: E402
from pratibimb.schema import RECORD_SPECS, SPEC_BY_PREFIX, trigger_names  # noqa: E402
from pratibimb.store import record_body, row_to_record  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
ap.add_argument("--record-id", required=True)
ap.add_argument("--column")
ap.add_argument("--value")
ap.add_argument("--mode", choices=["edit", "rewrite", "delete-chain-row"], default="edit")
a = ap.parse_args()

spec = next((s for p, s in SPEC_BY_PREFIX.items() if a.record_id.startswith(p)), None)
if spec is None:
    sys.exit("record id must start with ev_, in_, rl_ or dc_")
conn = sqlite3.connect(a.db, isolation_level=None)
conn.row_factory = sqlite3.Row
if conn.execute(f"SELECT 1 FROM {spec.table} WHERE {spec.pk}=?", (a.record_id,)).fetchone() is None:
    sys.exit(f"{a.record_id} not found")

print("[attacker] dropping append-only triggers (requires raw DB access)")
for name in trigger_names():
    conn.execute(f"DROP TRIGGER IF EXISTS {name}")

if a.mode == "delete-chain-row":
    conn.execute("DELETE FROM audit_chain WHERE record_id=?", (a.record_id,))
    print(f"[attacker] deleted chain row for {a.record_id}")
else:
    if not a.column or a.value is None:
        sys.exit("--column and --value are required for edit/rewrite")
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({spec.table})")}
    if a.column not in cols or a.column in ("prev_hash", "record_hash", spec.pk):
        sys.exit(f"column must be one of {sorted(cols - {'prev_hash', 'record_hash', spec.pk})}")
    old = conn.execute(f"SELECT {a.column} FROM {spec.table} WHERE {spec.pk}=?", (a.record_id,)).fetchone()[0]
    conn.execute(f"UPDATE {spec.table} SET {a.column}=? WHERE {spec.pk}=?", (a.value, a.record_id))
    print(f"[attacker] {spec.table}.{a.column}: {old!r} -> {a.value!r}")
    if a.mode == "rewrite":
        prev = GENESIS
        for link in conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall():
            s = RECORD_SPECS[link["record_type"]]
            rec = row_to_record(s, conn.execute(
                f"SELECT * FROM {s.table} WHERE {s.pk}=?", (link["record_id"],)).fetchone())
            new_hash = compute_hash(record_body(s, rec), prev)
            conn.execute(f"UPDATE {s.table} SET prev_hash=?, record_hash=? WHERE {s.pk}=?",
                         (prev, new_hash, link["record_id"]))
            conn.execute("UPDATE audit_chain SET prev_hash=?, record_hash=? WHERE seq=?",
                         (prev, new_hash, link["seq"]))
            prev = new_hash
        print("[attacker] recomputed every hash from genesis; new head =", prev)
print("[attacker] done. Now run: python3 scripts/verify_chain.py --db", a.db)
