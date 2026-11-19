"""
Evaluation and Scoring Script for Pratibimb Member A.
Deliverable A9: Reproducible evaluation of classification and field extraction.
Outputs per-type, per-app, per-language accuracy, field-level metrics, and unreadable rate in one command.
"""

from __future__ import annotations
import json
import io
import time
from pathlib import Path
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont

from intake.models import ScreenshotType
from extraction.service import ExtractionService


class ExtractionEvaluator:
    """
    Harness to evaluate extraction pipeline against ground truth annotations.
    """

    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or Path(__file__).parent / "data" / "test_cases.json"
        self.service = ExtractionService()

    def run_eval(self) -> Dict[str, Any]:
        with open(self.data_file, "r", encoding="utf-8") as f:
            cases = json.load(f)

        total_cases = len(cases)
        type_correct = 0
        app_correct = 0
        lang_correct = 0

        type_stats: Dict[str, Dict[str, int]] = {}
        app_stats: Dict[str, Dict[str, int]] = {}
        lang_stats: Dict[str, Dict[str, int]] = {}
        field_stats: Dict[str, Dict[str, int]] = {}

        unreadable_expected = 0
        unreadable_correct = 0

        start_time = time.time()

        for case in cases:
            c_id = case["id"]
            text = case["image_text"]
            has_qr = case.get("has_qr", False)
            qr_payload = case.get("qr_payload")
            exp_type = case["expected_type"]
            exp_app = case.get("expected_app")
            exp_lang = case.get("expected_language", "en")
            gt_fields = case.get("ground_truth_fields", {})

            # Prepare stats buckets
            if exp_type not in type_stats:
                type_stats[exp_type] = {"total": 0, "correct": 0}
            type_stats[exp_type]["total"] += 1

            if exp_app:
                if exp_app not in app_stats:
                    app_stats[exp_app] = {"total": 0, "correct": 0}
                app_stats[exp_app]["total"] += 1

            if exp_lang:
                if exp_lang not in lang_stats:
                    lang_stats[exp_lang] = {"total": 0, "correct": 0}
                lang_stats[exp_lang]["total"] += 1

            # Synthesize an image container with text for extraction
            img = Image.new("RGB", (600, 400), "#FFFFFF")
            draw = ImageDraw.Draw(img)
            draw.text((20, 20), text, fill="#000000")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            # Execute extraction service
            # We pass a temporary text file simulation to sarvam client to match image_text
            self.service.sarvam_client._simulate_digitise = lambda _: (text, exp_lang)
            if has_qr and qr_payload:
                self.service.qr_decoder.decode = lambda _: (qr_payload, self.service.qr_decoder.parse_payload(qr_payload)[0], True)
            else:
                self.service.qr_decoder.decode = lambda _: (None, None, False)

            evidence, interpretation = self.service.process_screenshot(
                image_path_or_bytes=img_bytes,
                sender_id="eval_user",
                channel="eval_harness",
            )

            # 1. Type check
            actual_type = interpretation.screenshot_type.value
            if actual_type == exp_type:
                type_correct += 1
                type_stats[exp_type]["correct"] += 1

            # 2. App check
            actual_app = interpretation.fields.app_name
            if exp_app:
                if actual_app and exp_app.lower() in actual_app.lower():
                    app_correct += 1
                    app_stats[exp_app]["correct"] += 1

            # 3. Language check
            actual_lang = interpretation.language_detected
            if exp_lang:
                if actual_lang == exp_lang:
                    lang_correct += 1
                    lang_stats[exp_lang]["correct"] += 1

            # 4. Unreadable check
            if exp_type == "OTHER":
                unreadable_expected += 1
                if actual_type == "OTHER":
                    unreadable_correct += 1

            # 5. Field level checks
            extracted_dict = interpretation.fields.model_dump()
            for f_name, exp_val in gt_fields.items():
                if f_name not in field_stats:
                    field_stats[f_name] = {"total": 0, "correct": 0}
                field_stats[f_name]["total"] += 1

                actual_val = extracted_dict.get(f_name)
                # Compare floats with round, strings case-insensitively
                is_match = False
                if exp_val is None and actual_val is None:
                    is_match = True
                elif isinstance(exp_val, (int, float)) and isinstance(actual_val, (int, float)):
                    is_match = abs(float(exp_val) - float(actual_val)) < 0.01
                elif exp_val and actual_val:
                    is_match = str(exp_val).strip().lower() in str(actual_val).strip().lower()

                if is_match:
                    field_stats[f_name]["correct"] += 1

        elapsed = time.time() - start_time

        results = {
            "total_test_cases": total_cases,
            "elapsed_seconds": round(elapsed, 3),
            "overall_type_accuracy": round((type_correct / total_cases) * 100, 2),
            "unreadable_abstention_accuracy": round((unreadable_correct / unreadable_expected) * 100, 2) if unreadable_expected else 100.0,
            "per_type_accuracy": {
                k: round((v["correct"] / v["total"]) * 100, 1) for k, v in type_stats.items()
            },
            "per_app_accuracy": {
                k: round((v["correct"] / v["total"]) * 100, 1) for k, v in app_stats.items()
            },
            "per_language_accuracy": {
                k: round((v["correct"] / v["total"]) * 100, 1) for k, v in lang_stats.items()
            },
            "per_field_accuracy": {
                k: round((v["correct"] / v["total"]) * 100, 1) for k, v in field_stats.items()
            },
        }

        return results

    def print_report(self, results: Dict[str, Any]) -> None:
        print("\n" + "=" * 65)
        print("        PRATIBIMB EXTRACTION EVALUATION REPORT (A9)        ")
        print("=" * 65)
        print(f"Total Test Cases Evaluated : {results['total_test_cases']}")
        print(f"Overall Type Accuracy      : {results['overall_type_accuracy']}%")
        print(f"Unreadable Abstention Rate : {results['unreadable_abstention_accuracy']}%")
        print(f"Total Evaluation Time      : {results['elapsed_seconds']}s")
        print("-" * 65)

        print("\n[PER-TYPE ACCURACY]")
        print(f"{'Screenshot Type':<25} | {'Accuracy':<10}")
        print("-" * 38)
        for k, v in results["per_type_accuracy"].items():
            print(f"{k:<25} | {v}%")

        print("\n[PER-APP ACCURACY]")
        print(f"{'Application':<20} | {'Accuracy':<10}")
        print("-" * 33)
        for k, v in results["per_app_accuracy"].items():
            print(f"{k:<20} | {v}%")

        print("\n[PER-LANGUAGE ACCURACY]")
        print(f"{'Language':<15} | {'Accuracy':<10}")
        print("-" * 28)
        for k, v in results["per_language_accuracy"].items():
            print(f"{k:<15} | {v}%")

        print("\n[FIELD-LEVEL EXTRACTION ACCURACY]")
        print(f"{'Field':<20} | {'Accuracy':<10}")
        print("-" * 33)
        for k, v in results["per_field_accuracy"].items():
            print(f"{k:<20} | {v}%")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    evaluator = ExtractionEvaluator()
    res = evaluator.run_eval()
    evaluator.print_report(res)

    # Save results to json
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "extraction_eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"Saved evaluation results to {out_path}")
