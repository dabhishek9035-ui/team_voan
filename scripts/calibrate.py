#!/usr/bin/env python3
"""Print false-accept, coverage and type-drift metrics for a labelled JSON file."""
import json
import sys

ROOT = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from pratibimb.calibration import calibrate, drift_report  # noqa: E402


def main(path):
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps({"thresholds": calibrate(payload.get("rows", payload)),
                      "drift": drift_report(payload.get("rows", payload),
                                             payload.get("baseline_types", {}))},
                     indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: calibrate.py LABELS.json")
    main(sys.argv[1])
