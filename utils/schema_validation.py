"""Validate a source document's own data against its vendored JSON Schema.

The one shared entry point every source-document generator calls before
writing its output - CALM, CycloneDX, SARIF, AsyncAPI, OpenAPI, ACT Rules,
Custom Elements Manifest, and DTCG all publish an official JSON Schema
(confirmed while charting docs/adr/0001-0029), so one generic validator
covers nearly every format this pipeline emits.
Details: docs/dev/utils/schema_validation.md#module
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


def validate_against_schema(data: Any, schema_path: str) -> None:
    """Raise `jsonschema.ValidationError` if `data` doesn't conform to the
    schema at `schema_path`. Raises nothing on success - callers that need
    a boolean should catch `jsonschema.ValidationError` themselves rather
    than this function swallowing it into one.

    `data` is whatever the schema's own root type is - an object for most
    of this pipeline's documents, an array for `tree.aria.schema.json`
    (docs/adr/0003), so this stays typed as `Any` rather than `Dict`.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)
