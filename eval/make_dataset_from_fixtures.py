"""
C2 helper: turn Member B's synthetic fixtures into eval ground truth (schema: eval/schema/ground_truth.schema.json).

  python eval/make_dataset_from_fixtures.py

This gives you a SYNTHETIC starter set so the harness runs today. Real, consented, masked screenshots and
AI-generated fakes (>= 2 generators, labelled by source) get added to eval/data/ground_truth.json by hand
following docs/labelling_guide.md. The split is by journey so a ticket and its payment never straddle
calibration and held-out.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = {"clean_journey": "clean", "refund_seen": "clean", "payment_no_ticket": "no_ticket",
         "exact_resend_same_sender": "duplicate", "cross_sender_reuse": "duplicate",
         "cropped_duplicate": "cropped", "out_of_window": "out_of_window", "suspect_notice": "suspect_notice",
         "inferred_only": "clean", "unmatched_refund": "unmatched", "ambiguous_two_candidates": "ambiguous"}


def split_for(journey):  # deterministic ~50/50 by journey; keep fixed so numbers are reproducible
    return "heldout" if int(hashlib.sha256(journey.encode()).hexdigest(), 16) % 2 else "calibration"


def build(mode="exact"):
    fx = json.load(open(ROOT / f"fixtures/fixtures_{mode}.json"))
    gt = json.load(open(ROOT / f"fixtures/ground_truth_{mode}.json"))
    ledger = fx["ledger"]
    interp = {r["evidence_id"]: r for r in ledger if r["kind"] == "interpretation"}
    rels = [r for r in ledger if r["kind"] == "relationship" and r["created_by"] == "fixture_seed"]
    sender_scn = {}
    for eid, g in gt.items():
        sender_scn.setdefault((g["sender_id"], g["scenario"]), []).append(eid)
    items = []
    for eid, g in gt.items():
        i = interp[eid]
        rel = next((r for r in rels if r["from_id"] == eid), None)
        e_rel = (g.get("expected_rels") or [{}])[0]
        tr = {"to": rel["to_id"] if rel and rel["to_id"] != eid else None,
              "type": {"EXACT": "EXACT", "INFERRED": "INFERRED"}.get(e_rel.get("type") or (rel or {}).get("type"), "NONE")}
        journey = f"{g['sender_id']}:{g['scenario']}"
        f = {k: v for k, v in i["fields"].items() if v is not None and k != "language_detected"}
        items.append({"item_id": eid, "split": split_for(journey), "source": "synthetic", "context": "metro_group_trip",
                      "screenshot_type": g["expected_type"], "app": i["fields"].get("app_name") or "unknown",
                      "language": i["language_detected"], "fields": f, "journey_id": journey,
                      "true_relationship": tr, "label": LABEL[g["scenario"]],
                      "should_clear": g.get("expected_decision_support", "needs_review") == "clear",
                      "dup_of": g.get("dup_of")})
    return items


if __name__ == "__main__":
    for mode in ("exact", "inferred_only"):
        items = build(mode)
        out = ROOT / f"eval/data/ground_truth_{mode}.json"
        json.dump(items, open(out, "w"), indent=2, ensure_ascii=False)
        n_h = sum(x["split"] == "heldout" for x in items)
        print(f"{mode}: {len(items)} items ({n_h} heldout, {len(items) - n_h} calibration) -> {out}")
    # NOTE: the harness default (eval/data/ground_truth.json) now comes from eval/make_dataset_from_manifest.py (data/ corpus).
    # These two files are for B's older fixture modes only.
