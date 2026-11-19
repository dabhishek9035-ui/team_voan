"""Loader for data/ (the synthetic corpus). Single place that knows the file layout."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Primary label for the eval schema, by priority (first match wins).
PRIORITY = [("fake", "fake"), ("suspect_notice", "suspect_notice"), ("out_of_window", "out_of_window"),
            ("cropped", "cropped"), ("duplicate", "duplicate"), ("no_ticket", "no_ticket"),
            ("unmatched", "unmatched"), ("inferred_pair", "inferred"), ("other", "other"), ("clean", "clean")]


def load(data_dir=DATA):
    d = Path(data_dir)
    m = json.load(open(d / "manifest.json", encoding="utf-8"))
    rel = json.load(open(d / "relationships.json", encoding="utf-8"))
    splits = json.load(open(d / "splits.json", encoding="utf-8"))
    cases = json.load(open(d / "demo_cases.json", encoding="utf-8"))
    trips = m["trip_windows"]
    day = {t["service_date"]: t["trip_id"] for t in trips}
    recs = []
    for r in m["records"]:
        gt = r["ground_truth_fields"]
        fields = {k: gt[k] for k in r["visible_fields"] if gt.get(k) is not None}
        trip_id = r["trip_id"] or day.get(r["received_at"][:10])      # trip-less items: assign by received date (join-code stand-in)
        recs.append({**r, "fields": fields, "all_fields": gt, "trip_id_raw": r["trip_id"], "trip_id": trip_id,
                     "language": gt.get("language_detected") or "en", "app": gt.get("app_name") or "unknown"})
    return {"manifest": m, "records": recs, "relationships": rel, "splits": splits, "demo_cases": cases, "trips": trips, "dir": d}


def primary_label(labels):
    for k, v in PRIORITY:
        if k in labels:
            return v
    return "clean"
