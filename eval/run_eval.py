"""
C5 evaluation harness. One command, three numbers (+ "where it fails").

  python eval/run_eval.py --split heldout          # real run: needs eval/data/predictions.json
  python eval/run_eval.py --selftest               # validates the SCORER only (predictions = truth)

Inputs
  eval/data/ground_truth.json   list of items (schema: eval/schema/ground_truth.schema.json)
  eval/data/predictions.json    optional "_meta": {producer, banner}; then {item_id: {screenshot_type, fields{}, relationship{to,type},
                                           decision_support: clear|needs_review|insufficient,
                                           latency_s?}}
  eval/data/timing.csv          condition(manual|pratibimb),participant,set_id,seconds,errors,missed_duplicates
  eval/data/drift.json          optional, produced by Member B's drift check

Rules baked in
  * Report only what is measured, with n. Never tune on the heldout split.
  * False-accept rate is ALWAYS printed with coverage (share auto-cleared) and its interval.
  * An item with no prediction counts as NOT cleared (conservative) and is counted separately.
"""
import argparse
import csv
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "eval/data"
OUT = ROOT / "eval/results"


# ---------------- helpers ----------------
def norm(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip().lower()
    try:
        return round(float(s.replace(",", "")), 2)
    except ValueError:
        return " ".join(s.split())


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - r) / d, 3), round((c + r) / d, 3)]


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": wilson(k, n)}


def true_link(t):
    return t["true_relationship"]["type"]  # EXACT | INFERRED | NONE


def pred_link(p):
    r = (p or {}).get("relationship") or {}
    t = r.get("type")
    return ("NONE" if t in (None, "UNMATCHED") else t), r.get("to")


# ---------------- metric 1 ----------------
def metric_accuracy(items, preds):
    by_type, by_app, by_lang = (defaultdict(lambda: [0, 0]) for _ in range(3))
    type_ok = [0, 0]
    unreadable, wrong = [], []
    for t in items:
        p = preds.get(t["item_id"])
        type_ok[1] += 1
        if p and p.get("screenshot_type") == t["screenshot_type"]:
            type_ok[0] += 1
        pf = (p or {}).get("fields") or {}
        for k, v in t["fields"].items():
            if k in ("currency",):
                continue
            ok = norm(pf.get(k)) == norm(v)
            for d, key in ((by_type, t["screenshot_type"]), (by_app, t["app"]), (by_lang, t["language"])):
                d[key][0] += ok
                d[key][1] += 1
            if not ok:
                (unreadable if pf.get(k) is None else wrong).append(
                    {"item": t["item_id"], "type": t["screenshot_type"], "field": k, "truth": v, "pred": pf.get(k)})
    link = defaultdict(lambda: [0, 0])
    bad_links, manual_skipped = [], []
    for t in items:
        tt = true_link(t)
        if tt == "MANUAL":          # a coordinator action, not something a machine can produce: reported, not scored
            manual_skipped.append(t["item_id"])
            continue
        pt, pto = pred_link(preds.get(t["item_id"]))
        ok = pt == tt and (tt == "NONE" or pto == t["true_relationship"].get("to"))
        link[tt][0] += ok
        link[tt][1] += 1
        if not ok:
            bad_links.append({"item": t["item_id"], "true": tt, "pred": pt, "scenario": t.get("label", "?")})
    fmt = lambda d: {k: rate(*v) for k, v in sorted(d.items())}
    return {"screenshot_type_accuracy": rate(*type_ok), "field_accuracy_by_type": fmt(by_type),
            "field_accuracy_by_app": fmt(by_app), "field_accuracy_by_language": fmt(by_lang),
            "linking_accuracy_by_true_type": fmt(link),
            "manual_links_not_machine_scorable": manual_skipped}, {"unreadable": unreadable, "wrong": wrong, "bad_links": bad_links}


# ---------------- metric 2 ----------------
def metric_false_accept(items, preds):
    bad = [t for t in items if not t["should_clear"]]
    good = [t for t in items if t["should_clear"]]
    cleared = lambda t: (preds.get(t["item_id"]) or {}).get("decision_support") == "clear"
    fa = [t for t in bad if cleared(t)]
    n_cleared = sum(cleared(t) for t in items)
    by_label = defaultdict(lambda: [0, 0])
    for t in bad:
        by_label[t["label"]][1] += 1
        by_label[t["label"]][0] += cleared(t)
    return {"false_accept": rate(len(fa), len(bad)),
            "false_accept_by_label": {k: rate(*v) for k, v in sorted(by_label.items())},
            "coverage_auto_cleared": rate(n_cleared, len(items)),
            "good_items_cleared": rate(sum(cleared(t) for t in good), len(good)),
            "items_without_prediction": sum(t["item_id"] not in preds for t in items),
            "note": "Report false-accept and coverage together. Holds only if new cases resemble calibration data."}, fa


# ---------------- metric 3 ----------------
def metric_time():
    f = D / "timing.csv"
    if not f.exists():
        return {"status": "not measured (no eval/data/timing.csv)"}
    rows = list(csv.DictReader(open(f)))
    out = {}
    for cond in ("manual", "pratibimb"):
        r = [x for x in rows if x["condition"] == cond]
        if r:
            s = [float(x["seconds"]) for x in r]
            out[cond] = {"n_runs": len(r), "median_seconds": st.median(s),
                         "errors_total": sum(int(x.get("errors") or 0) for x in r),
                         "missed_duplicates_total": sum(int(x.get("missed_duplicates") or 0) for x in r)}
    if "manual" in out and "pratibimb" in out:
        out["speedup_median"] = round(out["manual"]["median_seconds"] / out["pratibimb"]["median_seconds"], 2)
    return out or {"status": "timing.csv has no usable rows"}


# ---------------- where it fails ----------------
def where_it_fails(items, preds, detail, fa):
    lat = [p["latency_s"] for p in preds.values() if p.get("latency_s") is not None]
    missing_ids = [t["item_id"] for t in items if t["screenshot_type"] in ("TICKET_QR", "UPI_SUCCESS")
                   and not any(k in t["fields"] for k in ("ticket_id", "order_id", "utr"))]
    L = ["# Where it fails (from this run)", "",
         "| Failure mode | Count | Examples |", "|---|---|---|",
         f"| Key field unreadable (truth present, prediction null) | {len(detail['unreadable'])} | "
         + "; ".join(f"{x['item']}.{x['field']}" for x in detail['unreadable'][:5]) + " |",
         f"| Field read wrongly | {len(detail['wrong'])} | "
         + "; ".join(f"{x['item']}.{x['field']}" for x in detail['wrong'][:5]) + " |",
         f"| Link wrong or missed | {len(detail['bad_links'])} | "
         + "; ".join(f"{x['item']} ({x['scenario']}: true {x['true']}, got {x['pred']})" for x in detail['bad_links'][:5]) + " |",
         f"| Bad item auto-cleared (false accept) | {len(fa)} | "
         + "; ".join(f"{t['item_id']} ({t['label']}, source {t['source']})" for t in fa[:5]) + " |",
         f"| No shared identifier available | {len(missing_ids)} | " + ", ".join(missing_ids[:5]) + " |",
         f"| Latency (s), n={len(lat)} | - | " + (f"median {st.median(lat):.1f}, max {max(lat):.1f}" if lat else "not recorded") + " |",
         f"| Not auto-cleared (sent to a human or marked insufficient) | {sum(1 for t in items if (preds.get(t['item_id']) or {}).get('decision_support') != 'clear')} of {len(items)} | by design: duplicates, cases, INFERRED/UNMATCHED, notices, OTHER |",
         ]
    fpc = OUT / "fingerprint_check.json"
    if fpc.exists():
        L.append(f"| Perceptual hashes alone cannot separate duplicates from unrelated screens | see fingerprint_check.json | gated behind a semantic ID match; screenshot-of-screenshot is missed by hashes and caught only by ticket_id |")
    L += ["", "AI-generated fakes that passed are listed under false accept; add the generator name via `source`.",
          "Fakes in the synthetic corpus are hand-authored inconsistent mocks, not generator output: this table says nothing about AI-image fakes.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=str(D / "ground_truth.json"))
    ap.add_argument("--pred", default=str(D / "predictions.json"))
    ap.add_argument("--split", default="heldout", choices=["heldout", "calibration", "all"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    items = json.load(open(a.truth))
    if a.split != "all":
        items = [t for t in items if t["split"] == a.split]
    meta = {}
    if a.selftest:
        preds = {t["item_id"]: {"screenshot_type": t["screenshot_type"], "fields": t["fields"],
                                "relationship": {"to": t["true_relationship"].get("to"), "type": true_link(t)},
                                "decision_support": "clear" if t["should_clear"] else "needs_review"} for t in items}
        banner = "SELFTEST: predictions were copied from ground truth. This validates the scorer, NOT system performance."
    else:
        if not Path(a.pred).exists():
            raise SystemExit(f"No predictions at {a.pred}. Export them from the live system first.")
        preds = json.load(open(a.pred))
        meta = preds.pop("_meta", None) or {}
        banner = meta.get("banner")
    acc, detail = metric_accuracy(items, preds)
    fa, fa_items = metric_false_accept(items, preds)
    res = {"banner": banner, "split": a.split, "n_items": len(items),
           "sources": sorted({t["source"] for t in items}), "predictions_producer": (meta.get("producer") if not a.selftest else "selftest"),
           "metric1_extraction_and_linking": acc, "metric2_false_accept_with_coverage": fa,
           "metric3_coordinator_time": metric_time()}
    drift = D / "drift.json"
    res["drift_check"] = json.load(open(drift)) if drift.exists() else "not provided by Member B yet"
    OUT.mkdir(exist_ok=True)
    json.dump(res, open(OUT / "metrics.json", "w"), indent=2)
    (OUT / "where_it_fails.md").write_text(where_it_fails(items, preds, detail, fa_items))
    if banner:
        print("!!", banner)
    print(f"split={a.split} n={len(items)} sources={res['sources']}")
    print("false-accept:", fa["false_accept"], "\ncoverage    :", fa["coverage_auto_cleared"])
    print("by label    :", {k: f"{v['k']}/{v['n']}" for k, v in fa["false_accept_by_label"].items()})
    print("link accuracy:", {k: f"{v['k']}/{v['n']}" for k, v in acc["linking_accuracy_by_true_type"].items()})
    print("time:", res["metric3_coordinator_time"])
    print(f"-> {OUT}/metrics.json, where_it_fails.md")


if __name__ == "__main__":
    main()
