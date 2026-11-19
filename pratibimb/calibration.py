"""Small, auditable calibration and drift report for labelled records."""
from collections import Counter


def calibrate(rows, thresholds=(0.7, 0.8, 0.9, 0.95)):
    """Return false-accept rate and coverage for rows with score and accepted labels."""
    rows = list(rows)
    total_bad = sum(not bool(r["label"]) for r in rows)
    result = []
    for threshold in thresholds:
        selected = [r for r in rows if float(r["score"]) >= threshold]
        false_accepts = sum(not bool(r["label"]) for r in selected)
        result.append({"threshold": threshold, "false_accept_rate":
                       false_accepts / total_bad if total_bad else 0.0,
                       "coverage": len(selected) / len(rows) if rows else 0.0})
    return result


def drift_report(rows, baseline_types=None):
    current = Counter(r.get("type") for r in rows)
    baseline_types = baseline_types or {}
    total = sum(current.values()) or 1
    distribution = {key: value / total for key, value in current.items()}
    return {"distribution": distribution, "baseline": baseline_types,
            "new_types": sorted(set(current) - set(baseline_types))}
