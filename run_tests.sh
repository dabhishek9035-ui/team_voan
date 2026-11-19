#!/bin/sh
# One command to verify everything. Needs only Python 3 (standard library). Exit code 0 = all good.
cd "$(dirname "$0")" || exit 1
set -e
echo "### Python: $(python3 --version) | SQLite: $(python3 -c 'import sqlite3;print(sqlite3.sqlite_version)')"
echo; echo "### 1/3 Unit and integration tests"
python3 -m unittest discover -s tests -v 2>&1
echo; echo "### 2/3 End-to-end demo (seed, verify, append-only, correction, tamper, anchor)"
python3 scripts/demo_day1.py
echo; echo "### 3/3 Mutation check (break the engine on purpose; tests must notice)"
python3 scripts/mutation_check.py
echo; echo "### MEMBER B VERIFICATION: ALL PASSED"
