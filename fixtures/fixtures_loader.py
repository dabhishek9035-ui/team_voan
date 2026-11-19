"""
Fixture loader for Pratibimb test and evaluation fixtures.
Provides type-checked InterpretationRecord instances.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List
from intake.models import InterpretationRecord


def load_fixture_interpretations(fixtures_path: Optional[Path] = None) -> List[InterpretationRecord]:
    """Loads the 10 canonical fixture Interpretations."""
    if fixtures_path is None:
        fixtures_path = Path(__file__).parent / "interpretations.json"

    with open(fixtures_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [InterpretationRecord.model_validate(item) for item in data]


if __name__ == "__main__":
    records = load_fixture_interpretations()
    print(f"Loaded {len(records)} valid fixture Interpretation records:")
    for r in records:
        print(f" - [{r.screenshot_type.value}] {r.interp_id} (conf: {r.type_confidence:.2f})")
