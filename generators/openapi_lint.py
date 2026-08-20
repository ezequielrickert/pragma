"""A local stand-in for docs/adr/0004's vacuum/Spectral ruleset - this
repo has no Node.js toolchain and no CI to run either linter in
(confirmed: no package.json, no .github/workflows anywhere in the tree).
Wiring vacuum or Spectral is real, separate infrastructure work outside
what this ticket's own `DocumentGenerator` scope covers - a follow-up
ticket's job if the map wants it formally, not something to fake here.

What this module actually enforces, in plain Python, matching the base
ruleset docs/adr/0004 names: `operation-operationId-unique`,
`path-declarations-must-exist`, `operation-success-response`, plus
pragma's own custom rule (the `x-inference` extension's presence and
shape, checked against `schemas/openapi.x-inference.schema.json`).
`oas3-schema` itself is `openapi_spec_validator.validate` - a real
schema, not reimplemented here.

Findings are reported, not enforced as a hard failure: a finding like
"this operation never observed a 2xx response" describes what the crawl
found, not a bug in this generator - blocking document generation on it
would be exactly the kind of invented certainty this pipeline avoids
elsewhere (docs/adr/0001's reserved-field discipline).

Details: docs/dev/generators/openapi_lint.md#module
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from utils.schema_validation import validate_against_schema

_PATH_PARAM = re.compile(r"\{([^{}]+)\}")
_X_INFERENCE_SCHEMA_PATH = "schemas/openapi.x-inference.schema.json"


def _check_operation_ids_unique(document: Dict[str, Any]) -> List[str]:
    seen: Dict[str, str] = {}
    findings = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method not in ("get", "post", "put", "patch", "delete", "options", "head", "trace"):
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                continue
            location = f"{method.upper()} {path}"
            if operation_id in seen:
                findings.append(
                    f"operation-operationId-unique: '{operation_id}' used by both "
                    f"{seen[operation_id]} and {location}"
                )
            else:
                seen[operation_id] = location
    return findings


def _check_path_declarations_exist(document: Dict[str, Any]) -> List[str]:
    findings = []
    for path, item in document.get("paths", {}).items():
        template_names = set(_PATH_PARAM.findall(path))
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            declared = {
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "path"
            }
            missing = template_names - declared
            if missing:
                findings.append(
                    f"path-declarations-must-exist: {method.upper()} {path} names "
                    f"{sorted(missing)} in its path but declares no matching parameter"
                )
    return findings


def _check_operation_success_response(document: Dict[str, Any]) -> List[str]:
    findings = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            responses = operation.get("responses", {})
            has_success = any(code == "default" or code.startswith("2") for code in responses)
            if not has_success:
                findings.append(
                    f"operation-success-response: {method.upper()} {path} has no 2xx (or "
                    f"default) response - the crawl only ever observed this endpoint fail"
                )
    return findings


def _check_x_inference_shape(document: Dict[str, Any]) -> List[str]:
    findings = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            extension = operation.get("x-inference")
            if extension is None:
                findings.append(f"pragma-x-inference-present: {method.upper()} {path} has no x-inference extension")
                continue
            try:
                validate_against_schema(extension, _X_INFERENCE_SCHEMA_PATH)
            except Exception as exc:  # noqa: BLE001 - reported as a finding, not raised
                findings.append(f"pragma-x-inference-shape: {method.upper()} {path}: {exc}")
    return findings


def lint_openapi_document(document: Dict[str, Any]) -> List[str]:
    """Every finding the base ruleset (`operation-operationId-unique`,
    `path-declarations-must-exist`, `operation-success-response`) plus
    pragma's own `x-inference` check surface against `document` - empty
    when clean. `oas3-schema` itself is a separate, harder failure:
    `openapi_spec_validator.validate` in `generators/openapi.py`, run
    before this, since a document that isn't valid OpenAPI at all isn't
    worth linting further.
    Details: docs/dev/generators/openapi_lint.md#lint_openapi_document
    """
    return (
        _check_operation_ids_unique(document)
        + _check_path_declarations_exist(document)
        + _check_operation_success_response(document)
        + _check_x_inference_shape(document)
    )
