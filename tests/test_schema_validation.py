"""Unit tests for utils/schema_validation.py - the shared JSON Schema
validation entry point every source-document generator calls."""
import json

import jsonschema
import pytest

from utils.schema_validation import validate_against_schema

_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}


def test_conforming_data_raises_nothing(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(_SCHEMA), encoding="utf-8")

    validate_against_schema({"name": "coverage.json"}, str(schema_path))


def test_nonconforming_data_raises_validation_error(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(_SCHEMA), encoding="utf-8")

    with pytest.raises(jsonschema.ValidationError):
        validate_against_schema({"name": 123}, str(schema_path))
