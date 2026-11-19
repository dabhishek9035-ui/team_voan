import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard")); sys.path.insert(0, str(ROOT / "eval"))
from client import FixtureClient  # noqa
import run_eval as E  # noqa


def client(mode="exact"):
    return FixtureClient(ROOT / f"fixtures/fixtures_{mode}.json", ROOT / f"fixtures/ground_truth_{mode}.json")


def test_chain_ok_and_tamper_detected():
    c = client()
    assert c.audit_verify()["ok"]
    assert not c.tamper_demo()["result"]["ok"]


def test_decision_is_append_only_and_chain_stays_valid():
    c = client()
    n = len(c.ledger); first = c.ledger[0]["record_hash"]
    it = c.inbox("trip_001")["items"][0]
    c.post_decision(it["evidence_id"], "approved", "coord_01", "t")
    assert len(c.ledger) == n + 1 and c.ledger[0]["record_hash"] == first and c.audit_verify()["ok"]


def test_inferred_mode_has_no_exact_links_and_more_exceptions():
    a, b = client("exact").inbox("trip_001"), client("inferred_only").inbox("trip_001")
    assert b["needs_review"] > a["needs_review"]
    ci = client("inferred_only")
    assert not any(r["type"] == "EXACT" and r["reason"] == "Shared order_id" for r in ci._by("relationship"))


def test_no_level_claims_independent_verification():
    c = client()
    assert all("independently_verified" not in r["evidence_level"] for r in c.claims("trip_001"))


def test_claims_sorted_exact_before_inferred_unmatched():
    order = [r["relationship_type"] for r in client().claims("trip_001")]
    rank = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}
    assert [rank[x] for x in order] == sorted(rank[x] for x in order)


def test_false_accept_counts_wrongly_cleared_bad_items():
    items = [{"item_id": "a", "should_clear": False, "label": "fake", "source": "ai_fake:x"},
             {"item_id": "b", "should_clear": True, "label": "clean", "source": "real"}]
    preds = {"a": {"decision_support": "clear"}, "b": {"decision_support": "clear"}}
    r, fa = E.metric_false_accept(items, preds)
    assert r["false_accept"]["k"] == 1 and r["false_accept"]["n"] == 1 and r["coverage_auto_cleared"]["rate"] == 1.0
    # missing prediction counts as NOT cleared
    r2, _ = E.metric_false_accept(items, {})
    assert r2["false_accept"]["k"] == 0 and r2["items_without_prediction"] == 2


def test_link_accuracy_detects_wrong_target():
    t = {"item_id": "t", "fields": {}, "screenshot_type": "TICKET_QR", "app": "x", "language": "en",
         "true_relationship": {"to": "p1", "type": "EXACT"}}
    acc, d = E.metric_accuracy([t], {"t": {"relationship": {"to": "p2", "type": "EXACT"}, "screenshot_type": "TICKET_QR"}})
    assert acc["linking_accuracy_by_true_type"]["EXACT"]["k"] == 0 and d["bad_links"]


def test_forbidden_lint_clean():
    assert subprocess.run([sys.executable, str(ROOT / "tools/check_forbidden.py")]).returncode == 0
