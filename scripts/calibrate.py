#!/usr/bin/env python3
"""Print false-accept, coverage and type-drift metrics for a labelled JSON file.

Defaults to synthetic fixture scenarios when no file is passed (plumbing check only;
never treat synthetic fixture metrics as real-world performance).
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from pratibimb import Store, claims, linking, trust  # noqa: E402
from pratibimb.calibration import calibrate, drift_report  # noqa: E402
from pratibimb.config import load_config  # noqa: E402
from pratibimb.fixtures import load_into  # noqa: E402


def _synthetic_fixture_rows():
    """Build calibration rows from fixtures/scenarios.json for out-of-the-box B10 smoke checks."""
    cfg = load_config()
    store = Store(":memory:")
    try:
        index = load_into(store)
        trips = store.conn.execute("SELECT trip_id FROM trips").fetchall()
        trip_id = trips[0]["trip_id"]
        for scenario in index.values():
            for item in scenario["keys"].values():
                linking.link_interpretation(store, item["interp_id"], cfg)
        built = claims.build_claims(store, trip_id, cfg)
        rows = []
        trip = store.get_trip(trip_id)
        for c in built:
            a = trust.assess(store, c, cfg, trip)
            rows.append({
                "claim_ref": c["claim_ref"],
                "score": a["min_key_confidence"],
                "label": a["decision_support"] == "clear",
                "type": c["types"][c["root"]],
            })
        return rows
    finally:
        store.close()


def main(path=None):
    if path:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        rows = payload.get("rows", payload)
        baseline = payload.get("baseline_types", {})
        caveat = "Results hold only on data resembling the calibration set."
    else:
        from collections import Counter
        rows = _synthetic_fixture_rows()
        counts = Counter(r["type"] for r in rows)
        total = len(rows) or 1
        baseline = {t: c / total for t, c in counts.items()}
        caveat = "SYNTHETIC FIXTURES ONLY: plumbing check, not a measured real-world false-accept rate."

    print(json.dumps({
        "caveat": caveat,
        "thresholds": calibrate(rows),
        "drift": drift_report(rows, baseline),
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit("usage: calibrate.py [LABELS.json]")
    main(sys.argv[1] if len(sys.argv) == 2 else None)
