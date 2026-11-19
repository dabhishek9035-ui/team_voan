"""Edit one past ledger row in a COPY and show the chain break (C6 tamper demo, offline version).
For the live demo use B's tamper script + GET /audit/verify; this one proves the story without a server.

  python tamper/tamper_demo.py            # synthetic corpus ledger (default)
  python tamper/tamper_demo.py --fixtures # B's older fixture ledger"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from client import FixtureClient, SyntheticClient  # noqa: E402

c = FixtureClient(ROOT / "fixtures/fixtures_exact.json") if "--fixtures" in sys.argv else SyntheticClient()
print("before:", c.audit_verify())
d = c.tamper_demo()
print("edited:", d["edited"], f"(ledger index {d['edited_index']})")
print("after :", d["result"])
print("Tamper evidence, not prevention. Not a blockchain.")
