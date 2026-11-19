"""
Unit tests for Extraction JSON Schemas.
Validates all 9 schemas against JSON Schema Draft standard.
"""

import json
from pathlib import Path
import jsonschema
from intake.models import ScreenshotType


def test_all_schemas_exist_and_validate():
    schemas_dir = Path("extraction/schemas")
    assert schemas_dir.exists()

    all_types = [st.value for st in ScreenshotType]
    assert len(all_types) == 9

    for type_name in all_types:
        schema_path = schemas_dir / f"{type_name}.json"
        assert schema_path.exists(), f"Missing schema for {type_name}"

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = json.load(f)

        # Validate that the schema itself is a valid JSON Schema
        jsonschema.Draft202012Validator.check_schema(schema_data)
        assert schema_data.get("type") == "object"
        assert "properties" in schema_data
