#!/usr/bin/env python3
"""End-to-end Day-1 demonstration. Every step asserts; any failure exits non-zero."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from pratibimb import Store, ValidationError  # noqa: E402
from pratibimb.fixtures import load_into  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def step(msg):
    print(f"\n=== {msg}")


tmp = tempfile.mkdtemp(prefix="pratibimb_demo_")
db = os.path.join(tmp, "demo.db")

step("1. Seed a fresh database with the 11 synthetic scenarios")
r = run("scripts/load_fixtures.py", "--db", db)
print(r.stdout.strip())
assert r.returncode == 0, r.stderr
anchor = [l for l in r.stdout.splitlines() if l.startswith("anchor")][0].split("=")[1]
length = int([l for l in r.stdout.splitlines() if l.startswith("chain_length")][0].split("=")[1])

step("2. Verify the untouched chain (with the external anchor)")
r = run("scripts/verify_chain.py", "--db", db, "--anchor", anchor, "--length", str(length))
res = json.loads(r.stdout)
print(f"ok={res['ok']} checked={res['checked']} head={res['head_hash'][:16]}...")
assert r.returncode == 0 and res["ok"]

step("3. Append-only: the store has no way to change history, and the database refuses raw UPDATE/DELETE")
s = Store(db)
assert not any(hasattr(s, n) for n in ("update", "delete", "update_evidence", "delete_evidence", "remove"))
interp = s.list_records("interpretations")[0]
for sql in (f"UPDATE interpretations SET type_confidence=0 WHERE interp_id='{interp['interp_id']}'",
            f"DELETE FROM evidence WHERE evidence_id='{interp['evidence_id']}'"):
    try:
        s.conn.execute(sql)
        raise AssertionError("raw statement should have been refused")
    except Exception as e:
        assert "append-only" in str(e), e
        print("refused:", str(e))

step("4. A correction is a NEW record that supersedes the old one")
new = s.add_interpretation(interp["evidence_id"], "fixture:re-extraction", "fixtures-v2", interp["screenshot_type"],
                           0.99, interp["fields"], interp["field_confidence"], interp["field_source"],
                           supersedes=interp["interp_id"])
assert s.is_current(new) and not s.is_current(interp["interp_id"])
print(f"{interp['interp_id']} (superseded) -> {new} (current)")
try:
    s.add_interpretation(interp["evidence_id"], "x", "y", interp["screenshot_type"], 0.5, interp["fields"],
                         interp["field_confidence"], interp["field_source"], supersedes=interp["interp_id"])
    raise AssertionError("double supersede must fail")
except ValidationError as e:
    print("second correction of the same record refused:", e)
anchor2 = s.chain_head()
length2 = s.chain_length()
assert s.verify(expected_head=anchor2, expected_length=length2)["ok"]
s.close()

step("5. Tamper: edit one past row, bypassing the store")
target_store = Store(db)
target = target_store.list_records("interpretations")[5]["interp_id"]
target_store.close()
r = run("scripts/tamper.py", "--db", db, "--record-id", target, "--column", "type_confidence", "--value", "0.01")
print(r.stdout.strip())
assert r.returncode == 0, r.stderr
r = run("scripts/verify_chain.py", "--db", db, "--anchor", anchor2, "--length", str(length2))
res = json.loads(r.stdout)
print(json.dumps(res["first_break"], indent=1))
assert r.returncode == 1 and res["first_break"]["reason"] == "record_modified"
assert res["first_break"]["record_id"] == target

step("6. Honest limit: an attacker who rewrites the whole chain passes verify() but not the external anchor")
r = run("scripts/load_fixtures.py", "--db", db, "--force")
anchor3 = [l for l in r.stdout.splitlines() if l.startswith("anchor")][0].split("=")[1]
target_store = Store(db)
target = target_store.list_records("interpretations")[2]["interp_id"]
target_store.close()
run("scripts/tamper.py", "--db", db, "--record-id", target, "--column", "type_confidence", "--value", "0.01", "--mode", "rewrite")
without_anchor = json.loads(run("scripts/verify_chain.py", "--db", db).stdout)
with_anchor = json.loads(run("scripts/verify_chain.py", "--db", db, "--anchor", anchor3).stdout)
print("verify without anchor: ok =", without_anchor["ok"], " <- fooled")
print("verify with anchor:    ok =", with_anchor["ok"], with_anchor["first_break"]["reason"])
assert without_anchor["ok"] is True and with_anchor["ok"] is False and with_anchor["first_break"]["reason"] == "head_mismatch"

print("\nDAY 1 DEMO: ALL CHECKS PASSED")
