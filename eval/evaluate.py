#!/usr/bin/env python3
"""Score Member A/B outputs against Member C's labelled fixtures.

This evaluator does not create predictions. It requires a complete prediction
file for the selected split and keeps untimed coordinator work unreported.
All output from the bundled corpus is synthetic-only and must not be described
as a real-world performance result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIELD_NAMES = (
    "amount", "currency", "timestamp", "utr", "order_id", "ticket_id", "qr_payload",
    "origin_station", "destination_station", "fare", "payer_name_masked", "payee_name",
    "status_text", "app_name", "bank_name", "language_detected",
)
RELATIONSHIP_TYPES = ("EXACT", "INFERRED", "MANUAL", "UNMATCHED")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def normalize_pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def grouped_accuracy(rows: list[dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"record_count": len(rows)}
    correct_type = 0
    field_correct = 0
    field_total = 0
    present_correct = 0
    present_total = 0
    for row in rows:
        prediction = predictions[row["evidence_id"]]
        if prediction.get("screenshot_type") == row["screenshot_type"]:
            correct_type += 1
        actual_fields = row["ground_truth_fields"]
        predicted_fields = prediction.get("fields") or {}
        for field_name in FIELD_NAMES:
            actual = actual_fields.get(field_name)
            predicted = predicted_fields.get(field_name)
            field_total += 1
            if predicted == actual:
                field_correct += 1
            if actual is not None:
                present_total += 1
                if predicted == actual:
                    present_correct += 1
    result["screenshot_type_accuracy"] = rate(correct_type, len(rows))
    result["field_exact_accuracy_including_nulls"] = rate(field_correct, field_total)
    result["present_field_exact_accuracy"] = rate(present_correct, present_total)
    result["field_comparisons"] = field_total
    result["present_field_comparisons"] = present_total
    return result


def group_by(rows: list[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        grouped[str(key if key is not None else "(missing)")].append(row)
    return dict(sorted(grouped.items()))


def relationship_metrics(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
) -> dict[str, Any]:
    actual_by_pair: dict[tuple[str, str], str] = {}
    predicted_by_pair: dict[tuple[str, str], str] = {}
    for row in expected:
        actual_by_pair[normalize_pair(row["from_evidence_id"], row["to_evidence_id"])] = row["type"]
    for row in predicted:
        key = normalize_pair(row["from_evidence_id"], row["to_evidence_id"])
        if key in predicted_by_pair:
            raise ValueError(f"Duplicate predicted relationship for pair {key}.")
        predicted_by_pair[key] = row["type"]

    by_type: dict[str, Any] = {}
    all_types = sorted(set(RELATIONSHIP_TYPES) | set(actual_by_pair.values()) | set(predicted_by_pair.values()))
    for relationship_type in all_types:
        actual_keys = {pair for pair, value in actual_by_pair.items() if value == relationship_type}
        predicted_keys = {pair for pair, value in predicted_by_pair.items() if value == relationship_type}
        true_positive = len(actual_keys & predicted_keys)
        false_positive = len(predicted_keys - actual_keys)
        false_negative = len(actual_keys - predicted_keys)
        precision = rate(true_positive, true_positive + false_positive)
        recall = rate(true_positive, true_positive + false_negative)
        if precision is None or recall is None or precision + recall == 0:
            f1 = None
        else:
            f1 = round(2 * precision * recall / (precision + recall), 4)
        by_type[relationship_type] = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    exact_pair_and_type = sum(
        1 for pair, actual_type in actual_by_pair.items() if predicted_by_pair.get(pair) == actual_type
    )
    return {
        "expected_relationship_count": len(actual_by_pair),
        "predicted_relationship_count": len(predicted_by_pair),
        "exact_pair_and_type_accuracy": rate(exact_pair_and_type, len(actual_by_pair)),
        "by_relationship_type": by_type,
    }


def score_false_accepts(
    expected_cases: list[dict[str, Any]],
    predicted_claims: dict[str, dict[str, Any]],
    threshold: Any,
) -> dict[str, Any]:
    bad_cases = [case for case in expected_cases if case["is_bad"]]
    false_accepts = [case for case in bad_cases if predicted_claims[case["claim_case_id"]]["auto_clear"] is True]
    auto_cleared = [case for case in expected_cases if predicted_claims[case["claim_case_id"]]["auto_clear"] is True]
    return {
        "decision_threshold_used": threshold,
        "false_accept_count": len(false_accepts),
        "bad_claim_count": len(bad_cases),
        "false_accept_rate_among_bad_claims": rate(len(false_accepts), len(bad_cases)),
        "auto_cleared_count": len(auto_cleared),
        "claim_count": len(expected_cases),
        "coverage_auto_cleared": rate(len(auto_cleared), len(expected_cases)),
        "false_accepted_case_ids": [case["claim_case_id"] for case in false_accepts],
    }


def score_timings(expected_cases: list[dict[str, Any]], timing_path: Path | None) -> dict[str, Any]:
    if timing_path is None or not timing_path.exists():
        return {"status": "not_measured", "reason": "No timing file supplied.", "sample_count": 0}
    with timing_path.open(newline="", encoding="utf-8-sig") as handle:
        timing_rows = list(csv.DictReader(handle))
    timings = {row.get("claim_case_id", ""): row for row in timing_rows}
    expected_ids = [case["claim_case_id"] for case in expected_cases]
    missing: list[str] = []
    manual: list[float] = []
    system: list[float] = []
    for claim_id in expected_ids:
        row = timings.get(claim_id)
        if row is None or not row.get("manual_seconds") or not row.get("system_seconds"):
            missing.append(claim_id)
            continue
        try:
            manual_seconds = float(row["manual_seconds"])
            system_seconds = float(row["system_seconds"])
        except ValueError:
            missing.append(claim_id)
            continue
        if not math.isfinite(manual_seconds) or not math.isfinite(system_seconds) or min(manual_seconds, system_seconds) < 0:
            raise ValueError(f"Timing values must be finite, non-negative seconds for {claim_id}.")
        manual.append(manual_seconds)
        system.append(system_seconds)
    if missing:
        return {
            "status": "incomplete",
            "reason": "Coordinator time is reported only when both timings exist for every case in the selected split.",
            "sample_count": len(expected_ids) - len(missing),
            "required_count": len(expected_ids),
            "missing_case_ids": missing,
        }
    manual_total = sum(manual)
    system_total = sum(system)
    return {
        "status": "measured",
        "sample_count": len(expected_ids),
        "manual_total_seconds": round(manual_total, 2),
        "system_total_seconds": round(system_total, 2),
        "manual_mean_seconds": round(manual_total / len(expected_ids), 2) if expected_ids else None,
        "system_mean_seconds": round(system_total / len(expected_ids), 2) if expected_ids else None,
        "time_change_percent": round((system_total - manual_total) / manual_total * 100, 2) if manual_total else None,
        "interpretation": "Negative time change means the system session took less time; it does not establish causation.",
    }


def evaluate(
    manifest_path: Path,
    relationships_path: Path,
    cases_path: Path,
    predictions_path: Path,
    split: str,
    timings_path: Path | None,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    relationships = load_json(relationships_path)
    claim_cases = load_json(cases_path)
    predictions_doc = load_json(predictions_path)
    if predictions_doc.get("split") != split:
        raise ValueError(f"Prediction split must be {split!r}.")
    threshold = predictions_doc.get("decision_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
        raise ValueError("Prediction file must include decision_threshold between 0 and 1.")

    expected_records = [row for row in manifest["records"] if row["split"] == split]
    expected_ids = {row["evidence_id"] for row in expected_records}
    record_predictions: dict[str, dict[str, Any]] = {}
    for prediction in predictions_doc.get("records", []):
        evidence_id = prediction.get("evidence_id")
        if evidence_id not in expected_ids:
            raise ValueError(f"Unexpected prediction evidence ID in split {split}: {evidence_id}.")
        if evidence_id in record_predictions:
            raise ValueError(f"Duplicate prediction for evidence ID {evidence_id}.")
        record_predictions[evidence_id] = prediction
    missing_records = sorted(expected_ids - set(record_predictions))
    if missing_records:
        raise ValueError("Predictions must cover every record in the split. Missing: " + ", ".join(missing_records))

    expected_relations = [
        relation for relation in relationships
        if relation["from_evidence_id"] in expected_ids and relation["to_evidence_id"] in expected_ids
    ]
    predicted_relations = predictions_doc.get("relationships", [])
    for relation in predicted_relations:
        if relation.get("type") not in RELATIONSHIP_TYPES:
            raise ValueError(f"Invalid predicted relationship type: {relation.get('type')}.")
        if relation.get("from_evidence_id") not in expected_ids or relation.get("to_evidence_id") not in expected_ids:
            raise ValueError("Predicted relationships must use evidence IDs from the selected split.")

    expected_cases = [case for case in claim_cases if case["split"] == split]
    expected_case_ids = {case["claim_case_id"] for case in expected_cases}
    predicted_claims: dict[str, dict[str, Any]] = {}
    for claim in predictions_doc.get("claims", []):
        claim_id = claim.get("claim_case_id")
        if claim_id not in expected_case_ids:
            raise ValueError(f"Unexpected claim prediction in split {split}: {claim_id}.")
        if claim_id in predicted_claims:
            raise ValueError(f"Duplicate claim prediction for {claim_id}.")
        if not isinstance(claim.get("auto_clear"), bool):
            raise ValueError(f"Claim prediction {claim_id} needs a boolean auto_clear value.")
        predicted_claims[claim_id] = claim
    missing_claims = sorted(expected_case_ids - set(predicted_claims))
    if missing_claims:
        raise ValueError("Predictions must cover every claim case in the split. Missing: " + ", ".join(missing_claims))

    by_type = group_by(expected_records, lambda row: row["screenshot_type"])
    by_app = group_by(expected_records, lambda row: row["ground_truth_fields"].get("app_name"))
    by_language = group_by(expected_records, lambda row: row["ground_truth_fields"].get("language_detected"))

    return {
        "dataset": manifest["dataset_name"],
        "synthetic_only": bool(manifest.get("synthetic_only")),
        "valid_for_real_world_claims": False,
        "split": split,
        "record_count": len(expected_records),
        "claim_case_count": len(expected_cases),
        "metrics": {
            "extraction_and_linking": {
                "overall": grouped_accuracy(expected_records, record_predictions),
                "by_screenshot_type": {
                    key: grouped_accuracy(rows, record_predictions) for key, rows in by_type.items()
                },
                "by_app": {
                    key: grouped_accuracy(rows, record_predictions) for key, rows in by_app.items()
                },
                "by_language": {
                    key: grouped_accuracy(rows, record_predictions) for key, rows in by_language.items()
                },
                "relationships": relationship_metrics(expected_relations, predicted_relations),
            },
            "false_accept_with_coverage": score_false_accepts(expected_cases, predicted_claims, threshold),
            "coordinator_time": score_timings(expected_cases, timings_path),
        },
        "caveat": "Synthetic fixture scores check evaluator plumbing only; they do not estimate performance on real cases.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("calibration", "heldout"), default="heldout")
    parser.add_argument("--predictions", type=Path, required=True, help="Member A/B output JSON; no defaults are generated.")
    parser.add_argument("--timings", type=Path, default=None, help="Optional coordinator timing CSV for the same split.")
    parser.add_argument("--output", type=Path, default=None, help="Optional path for JSON metrics; stdout if omitted.")
    parser.add_argument("--manifest", type=Path, default=DATA / "manifest.json")
    parser.add_argument("--relationships", type=Path, default=DATA / "relationships.json")
    parser.add_argument("--cases", type=Path, default=DATA / "evaluation_cases.json")
    args = parser.parse_args()
    try:
        result = evaluate(args.manifest, args.relationships, args.cases, args.predictions, args.split, args.timings)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Evaluation stopped: {error}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
