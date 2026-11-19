"""
C2: build eval ground truth from data/ (synthetic corpus, 30 screenshots).

  python eval/make_dataset_from_manifest.py

Writes eval/data/ground_truth.json (schema: eval/schema/ground_truth.schema.json) and
eval/data/evaluation_cases.json (derived here: data/README mentions this file but it was not in the zip).

Splits come from data/splits.json (by trip window), NOT from a hash. Truth per item:
  true_relationship = the relationship whose `from` is this item (direction convention in standin/engine.py);
  type NONE if the item has no outgoing relationship or it is UNMATCHED. MANUAL is kept as MANUAL (not machine-scorable).
  should_clear = clean label AND its outgoing links and its incoming non-duplicate EXACT/INFERRED links are all
                 EXACT + auto_clear_eligible, with at least one link. A later duplicate or a bad claim pointing AT a
                 clean ticket does not make that ticket unclearable (the duplicate/claim is its own item).
                 Inferred pairs, duplicates, cases, fakes, notices and OTHER are never clearable.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from standin.dataset import load, primary_label  # noqa: E402


def build():
    D = load()
    sp = D["splits"]
    cal, held = set(sp["calibration_evidence_ids"]), set(sp["heldout_evidence_ids"])
    rels = D["relationships"]
    items = []
    for r in D["records"]:
        eid = r["evidence_id"]
        assert (eid in cal) != (eid in held), f"{eid} must be in exactly one split"
        split = "calibration" if eid in cal else "heldout"
        assert split == r["split"], f"{eid}: manifest split {r['split']} != splits.json {split}"
        out = next((x for x in rels if x["from_evidence_id"] == eid), None)
        outs = [x for x in rels if x["from_evidence_id"] == eid]
        dupish = lambda x: any(b in ("sha256", "perceptual_similarity") for b in x["basis"])
        ins = [x for x in rels if x["to_evidence_id"] == eid and x["type"] in ("EXACT", "INFERRED") and not dupish(x)]
        labels = r["labels"]
        ok = lambda x: x["type"] == "EXACT" and x["auto_clear_eligible"]
        should_clear = ("clean" in labels and "inferred_pair" not in labels and all(ok(x) for x in outs + ins)
                        and bool(outs or ins))
        t = out["type"] if out else "NONE"
        items.append({
            "item_id": eid, "split": split, "source": "synthetic", "context": "metro_group_trip",
            "screenshot_type": r["screenshot_type"], "app": r["app"], "language": r["language"],
            "fields": {k: v for k, v in r["fields"].items() if k not in ("language_detected",)},
            "journey_id": r["journey_id"] or f"{r['sender_id']}:{r['scenario_id']}", "trip_id": r["trip_id"],
            "true_relationship": {"to": out["to_evidence_id"] if out else None, "type": "NONE" if t == "UNMATCHED" else t},
            "label": primary_label(labels), "labels_raw": labels, "variant": r["variant"],
            "should_clear": should_clear, "dup_of": r["variant_of"],
        })
    return items


def evaluation_cases(items):
    return [{"item_id": i["item_id"], "split": i["split"], "label": i["label"], "should_clear": i["should_clear"],
             "why": ("clean item whose links are all EXACT and auto-clear eligible" if i["should_clear"]
                     else f"must not auto-clear ({', '.join(i['labels_raw'])})")} for i in items]


if __name__ == "__main__":
    items = build()
    out = ROOT / "eval/data"
    json.dump(items, open(out / "ground_truth.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(evaluation_cases(items), open(out / "evaluation_cases.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    n_h = sum(i["split"] == "heldout" for i in items)
    n_c = sum(i["should_clear"] for i in items)
    print(f"{len(items)} items ({n_h} heldout, {len(items) - n_h} calibration), {n_c} clearable -> {out}/ground_truth.json")
