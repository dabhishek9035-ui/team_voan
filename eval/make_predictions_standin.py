"""
Write eval/data/predictions.json from the rule-based stand-in engine (standin/engine.py).

  python eval/make_predictions_standin.py            # all splits, each run independently (no cross-split sightings)

Inputs to the engine are ORACLE fields (ground truth copied), so field accuracy is trivially 100% and says nothing
about Member A's extraction. What IS exercised for real: linking rules, flags, clear/needs_review decisions and the
scorer, on the synthetic corpus. The banner below is carried into metrics.json and shown on the dashboard.
Replace this file with predictions exported from the live system (B's decisions + A's extraction) for a real run.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from standin import engine  # noqa: E402
from standin.dataset import load  # noqa: E402

BANNER = ("STAND-IN RUN: predictions come from a rule-based reference engine fed ORACLE (ground-truth) fields on a small "
          "hand-authored synthetic corpus. This checks the plumbing and the rules. It is NOT system accuracy, NOT a "
          "false-accept rate for the real system, and NOT a coordinator time result. The rules were written after reading both "
          "splits, so even the 'held-out' rows are not a blind test of them.")


def main():
    D = load()
    preds = {"_meta": {"producer": "standin.engine (rules) + oracle fields", "banner": BANNER}}
    for split in ("calibration", "heldout"):
        recs = [r for r in D["records"] if r["split"] == split]
        obs = [engine.observable(r) for r in recs]
        res = engine.analyse(obs, D["trips"])
        for r in recs:
            a = res[r["evidence_id"]]
            link = a["link"]
            preds[r["evidence_id"]] = {
                "screenshot_type": r["screenshot_type"],
                "fields": {k: v for k, v in r["fields"].items() if k != "language_detected"},
                "relationship": {"to": link["to"] if link else None, "type": link["type"] if link else "UNMATCHED"},
                "decision_support": a["decision_support"], "flags": a["flags"]}
    out = ROOT / "eval/data/predictions.json"
    json.dump(preds, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    n_clear = sum(1 for k, v in preds.items() if k != "_meta" and v["decision_support"] == "clear")
    print(f"{len(preds) - 1} predictions ({n_clear} clear) -> {out}")


if __name__ == "__main__":
    main()
