"""Unit tests for generators/openapi_lint.py - pure logic over an
already-built OpenAPI document, no graph store needed."""
from generators.openapi_lint import lint_openapi_document

_VALID_X_INFERENCE = {
    "observation_count": 3,
    "methods_observed": ["GET"],
    "methods_inferred": [],
    "confidence": {"path_params": 1.0, "request_schema": 0.0, "response_schema": 0.6},
}


def _document(paths):
    return {"openapi": "3.1.0", "info": {"title": "x", "version": "1.0.0"}, "paths": paths}


def _clean_operation(operation_id="getOrder", **overrides):
    operation = {
        "operationId": operation_id,
        "responses": {"200": {"description": "ok"}},
        "x-inference": _VALID_X_INFERENCE,
    }
    operation.update(overrides)
    return operation


def test_a_clean_document_has_no_findings():
    document = _document({"/orders/{orderId}": {"get": _clean_operation(
        parameters=[{"name": "orderId", "in": "path", "required": True, "schema": {"type": "string"}}],
    )}})

    assert lint_openapi_document(document) == []


def test_duplicate_operation_ids_are_reported():
    document = _document({
        "/orders/{id}": {"get": _clean_operation("getOrder")},
        "/legacy-orders/{id}": {"get": _clean_operation("getOrder")},
    })

    findings = lint_openapi_document(document)

    assert any("operation-operationId-unique" in f for f in findings)


def test_a_path_parameter_with_no_matching_declaration_is_reported():
    document = _document({"/orders/{orderId}": {"get": _clean_operation(parameters=[])}})

    findings = lint_openapi_document(document)

    assert any("path-declarations-must-exist" in f for f in findings)


def test_an_operation_with_only_failure_responses_is_reported():
    document = _document({"/orders": {"get": _clean_operation(
        responses={"500": {"description": "Observed response (HTTP 500)."}},
    )}})

    findings = lint_openapi_document(document)

    assert any("operation-success-response" in f for f in findings)


def test_a_default_response_counts_as_success():
    document = _document({"/orders": {"get": _clean_operation(
        responses={"default": {"description": "No response status was captured."}},
    )}})

    assert not any("operation-success-response" in f for f in lint_openapi_document(document))


def test_a_missing_x_inference_extension_is_reported():
    operation = _clean_operation()
    del operation["x-inference"]
    document = _document({"/orders": {"get": operation}})

    findings = lint_openapi_document(document)

    assert any("pragma-x-inference-present" in f for f in findings)


def test_a_malformed_x_inference_extension_is_reported():
    document = _document({"/orders": {"get": _clean_operation(
        **{"x-inference": {"observation_count": "not-a-number"}},
    )}})

    findings = lint_openapi_document(document)

    assert any("pragma-x-inference-shape" in f for f in findings)
