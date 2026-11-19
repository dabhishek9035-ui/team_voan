#!/usr/bin/env python3
"""Mutation check: break the engine on purpose and confirm the test suite notices.

Each mutation is applied to a throw-away COPY of the project. A mutation that the suite does NOT
catch ("SURVIVED") means a missing test, and this script exits non-zero.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

MUTATIONS = [
    ("audit: stop recomputing record hashes", "pratibimb/audit.py",
     "if compute_hash(record_body(spec, rec), rec[\"prev_hash\"]) != rec[\"record_hash\"]:", "if False:"),
    ("audit: stop checking chain continuity", "pratibimb/audit.py",
     "if link[\"prev_hash\"] != prev:", "if False:"),
    ("audit: stop detecting gaps", "pratibimb/audit.py", "if seq != expected_seq:", "if False:"),
    ("audit: stop detecting orphans", "pratibimb/audit.py", "if first_break is None and orphans:", "if False:"),
    ("audit: ignore the external anchor", "pratibimb/audit.py",
     "if first_break is None and expected_head is not None and prev != expected_head:", "if False:"),
    ("audit: stop comparing chain hash to record hash", "pratibimb/audit.py",
     "if link[\"record_hash\"] != rec[\"record_hash\"]:", "if False:"),
    ("store: remove append-only triggers", "pratibimb/store.py",
     "self.conn.executescript(trigger_sql())", "pass"),
    ("store: allow branching supersedes", "pratibimb/store.py", "if taken:", "if False:"),
    ("store: do not coerce confidence to float", "pratibimb/validate.py", "return float(value)", "return value"),
    ("store: write the chain row with a wrong prev hash", "pratibimb/store.py",
     "(spec.table, rid, prev, record_hash, values[\"created_at\"])", "(spec.table, rid, GENESIS, record_hash, values[\"created_at\"])"),
    ("canon: unsorted keys", "pratibimb/canon.py", "sort_keys=True", "sort_keys=False"),
    ("validate: allow null with confidence", "pratibimb/validate.py", "if c != 0.0:", "if False:"),
    ("validate: allow a machine-made MANUAL link", "pratibimb/store.py",
     "if not created_by.startswith(\"coordinator:\"):\n                raise ValidationError(\"MANUAL", "if False:\n                raise ValidationError(\"MANUAL"),
    ("validate: allow non-human decisions", "pratibimb/store.py",
     "if not decided_by.startswith(\"coordinator:\"):", "if False:"),
    ("store: skip evidence-existence check on interpretations", "pratibimb/store.py",
     "lambda: self._need(\"evidence\", \"evidence_id\", evidence_id, \"evidence\"),\n            lambda: self._check_supersedes(spec, supersedes),\n            same_evidence",
     "lambda: None,\n            lambda: self._check_supersedes(spec, supersedes),\n            same_evidence"),
    ("store: do not roll back on failure", "pratibimb/store.py",
     "except sqlite3.IntegrityError as e:\n                self.conn.execute(\"ROLLBACK\")", "except sqlite3.IntegrityError as e:\n                self.conn.execute(\"COMMIT\")"),
    ("store: re-extraction may jump to other evidence", "pratibimb/store.py",
     "if old and old[\"evidence_id\"] != evidence_id:", "if False:"),
]


def main():
    survived = []
    for name, rel, old, new in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="mut_")
        dst = os.path.join(tmp, "p")
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "*.db", ".git"))
        path = os.path.join(dst, rel)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if old not in src:
            print(f"?? could not apply mutation (text not found): {name}")
            survived.append(name)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src.replace(old, new, 1))
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                           cwd=dst, capture_output=True, text=True, timeout=300)
        caught = r.returncode != 0
        print(f"{'CAUGHT  ' if caught else 'SURVIVED'}  {name}")
        if not caught:
            survived.append(name)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} mutations caught")
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
