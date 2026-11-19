import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "dashboard")); sys.path.insert(0, str(ROOT / "eval"))
import pytest  # noqa: E402
from standin import engine  # noqa: E402
from standin.dataset import load, DATA  # noqa: E402
from standin.fingerprints import sha256_file  # noqa: E402
import make_dataset_from_manifest as MD  # noqa: E402
import run_eval as E  # noqa: E402
from client import SyntheticClient  # noqa: E402

D = load()
RECS = {r["evidence_id"]: r for r in D["records"]}


def test_corpus_shape_and_files():
    assert len(RECS) == 30 and D["manifest"]["synthetic_only"] is True
    assert all((DATA / r["image_file"]).exists() for r in RECS.values())


def test_sha256_matches_manifest():
    assert all(sha256_file(DATA / r["image_file"]) == r["sha256"] for r in RECS.values())


def test_splits_partition_and_no_relationship_crosses_a_split():
    sp = D["splits"]
    cal, held = set(sp["calibration_evidence_ids"]), set(sp["heldout_evidence_ids"])
    assert not cal & held and cal | held == set(RECS)
    for x in D["relationships"]:
        assert RECS[x["from_evidence_id"]]["split"] == RECS[x["to_evidence_id"]]["split"]


def test_all_four_relationship_types_present():
    assert {x["type"] for x in D["relationships"]} == {"EXACT", "INFERRED", "MANUAL", "UNMATCHED"}


def test_ground_truth_clearable_set_is_what_we_expect():
    items = MD.build()
    clear = {i["item_id"][-7:] for i in items if i["should_clear"]}
    assert clear == {"CAL-001", "CAL-002", "CAL-003", "CAL-004", "EST-016", "EST-017", "EST-018"}
    assert all(not i["should_clear"] for i in items if i["label"] in ("duplicate", "cropped", "fake", "inferred", "other", "suspect_notice"))


def test_engine_reads_only_observables():
    o = engine.observable(RECS["SYN-E-CAL-001"])
    assert set(o) == {"evidence_id", "sender_id", "received_at", "trip_id", "type", "fields", "sha256", "phash", "ahash"}


def _run(split):
    recs = [r for r in D["records"] if r["split"] == split]
    return engine.analyse([engine.observable(r) for r in recs], D["trips"])


@pytest.mark.parametrize("split", ["calibration", "heldout"])
def test_engine_never_clears_a_bad_item_and_inferred_never_clears(split):
    truth = {i["item_id"]: i for i in MD.build()}
    for eid, a in _run(split).items():
        if a["decision_support"] == "clear":
            assert truth[eid]["should_clear"], eid
            assert a["relationship_type"] == "EXACT"
        if a["relationship_type"] == "INFERRED":
            assert a["decision_support"] != "clear"


def test_engine_specific_behaviours():
    a = _run("heldout")
    assert "perceptual_similar" in a["SYN-E-TEST-019"]["flags"]
    assert "perceptual_similar" not in a["SYN-E-TEST-020"]["flags"]      # hash distance 24: caught only by ticket_id
    assert "same_sender_resend" in a["SYN-E-TEST-020"]["flags"]
    assert a["SYN-E-TEST-029"]["relationship_type"] == "UNMATCHED"       # same amount+minute, other sender: not guessed
    assert "fare_mismatch" in a["SYN-E-TEST-026"]["flags"]
    assert "date_outside_window" in a["SYN-E-TEST-028"]["flags"]
    assert a["SYN-E-TEST-021"]["case_ref"] and a["SYN-E-TEST-022"]["case_ref"] == a["SYN-E-TEST-021"]["case_ref"]
    assert all(v["evidence_level"]["payment_debit"] != "independently_verified" for v in a.values())


def test_compute_links_matches_authored_relationships_except_manual():
    truth = {(x["from_evidence_id"], x["to_evidence_id"]): x["type"] for x in D["relationships"]}
    for split in ("calibration", "heldout"):
        recs = [engine.observable(r) for r in D["records"] if r["split"] == split]
        got = {(l["from"], l["to"]): l["type"] for l in engine.compute_links(recs)}
        for k, t in truth.items():
            if RECS[k[0]]["split"] == split and t != "MANUAL":
                assert got.get(k) == t, (k, t, got.get(k))
        assert not [k for k, t in got.items() if k not in truth and t != "UNMATCHED"], "engine invented a link"


def test_scorer_on_standin_predictions_skips_manual_and_reports_coverage():
    items = [i for i in MD.build() if i["split"] == "heldout"]
    obs = [engine.observable(RECS[i["item_id"]]) for i in items]
    res = engine.analyse(obs, D["trips"])
    preds = {i["item_id"]: {"screenshot_type": i["screenshot_type"], "fields": i["fields"],
                            "relationship": {"to": (res[i["item_id"]]["link"] or {}).get("to"),
                                             "type": (res[i["item_id"]]["link"] or {}).get("type", "UNMATCHED")},
                            "decision_support": res[i["item_id"]]["decision_support"]} for i in items}
    acc, _ = E.metric_accuracy(items, preds)
    assert "SYN-E-TEST-026" in acc["manual_links_not_machine_scorable"]
    fa, _ = E.metric_false_accept(items, preds)
    assert fa["false_accept"]["k"] == 0 and fa["coverage_auto_cleared"]["n"] == 15


# ---------------- SyntheticClient ----------------
def test_client_chain_decisions_and_tamper():
    c = SyntheticClient()
    assert c.audit_verify()["ok"] and not c.tamper_demo()["result"]["ok"]
    n, first = len(c.ledger), c.ledger[0]["record_hash"]
    it = c.inbox("SYN-TRIP-HELDOUT-01")["items"][0]
    before = c.inbox("SYN-TRIP-HELDOUT-01")["needs_review"]
    c.post_decision(it["evidence_id"], "approved", "coord_01", "t")
    assert len(c.ledger) == n + 1 and c.ledger[0]["record_hash"] == first and c.audit_verify()["ok"]
    assert c.inbox("SYN-TRIP-HELDOUT-01")["needs_review"] == before - 1


def test_client_manual_link_supersedes_and_stays_chained():
    c = SyntheticClient()
    c.post_decision("SYN-E-TEST-029", "link_manually", "coord_01", "same person confirmed", link_to="SYN-E-TEST-017")
    rel = [r for r in c._rels() if r["from_id"] == "SYN-E-TEST-029"]
    assert len(rel) == 1 and rel[0]["type"] == "MANUAL" and rel[0]["supersedes"] == "SYN-R-017"
    assert c.audit_verify()["ok"]


def test_client_inbox_rows_carry_type_and_levels_and_never_clear_inferred():
    c = SyntheticClient()
    for t in c.trips_list():
        ib = c.inbox(t["trip_id"])
        assert ib["needs_review"] < ib["total_screenshots"]
        for it in ib["items"]:
            assert it["relationship_type"] in ("EXACT", "INFERRED", "MANUAL", "UNMATCHED") and it["evidence_level"] and it["reasons"]
            assert it["decision_support"] != "clear"


def test_client_claims_sorted_and_marked():
    for t in SyntheticClient().trips_list():
        rows = SyntheticClient().claims(t["trip_id"])
        rank = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}
        assert [rank[r["relationship_type"]] for r in rows] == sorted(rank[r["relationship_type"]] for r in rows)
        assert all("independently_verified" not in r["evidence_level"] for r in rows)


def test_trail_has_no_image_path_and_image_access_is_logged():
    c = SyntheticClient()
    assert "file_ref" not in c.trail("SYN-E-CAL-001")["evidence"]
    with pytest.raises(ValueError):
        c.image_path("SYN-E-CAL-001", "coord_01", "  ")
    p = c.image_path("SYN-E-CAL-001", "coord_01", "checking synthetic sample")
    assert Path(p).exists() and c.access_log[-1]["evidence_id"] == "SYN-E-CAL-001"


def test_dashboard_renders_every_view_for_every_source():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=60).run()
    for src in ["Synthetic dataset (30 screenshots)", "Fixtures: exact IDs", "Fixtures: inferred-only"]:
        at.sidebar.radio[0].set_value(src).run()
        assert not at.exception, (src, at.exception)
        for v in at.sidebar.radio[1].options:
            at.sidebar.radio[1].set_value(v).run()
            assert not at.exception, (src, v, [str(e.value)[:200] for e in at.exception])
