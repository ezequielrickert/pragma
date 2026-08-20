"""Unit tests for the OpenAPI document (generators/openapi.py and
json_schema.py). Fully deterministic - no model, no browser, no store."""
import json

import pytest
import yaml

from core.interfaces import InferredRequest
from generators.json_schema import schema_from_shape
from generators.openapi import build_openapi_document, path_template

openapi_spec_validator = pytest.importorskip("openapi_spec_validator")


def _request(method="GET", endpoint="api.example.com/orders", **extra):
    defaults = dict(
        query_params=(), body_shape="", response_shape="", triggered_by=(),
        loaded_by=(), status_codes=(200,), latencies_ms=(),
    )
    defaults.update(extra)
    return InferredRequest(method=method, endpoint=endpoint, **defaults)


def _document(*requests):
    return build_openapi_document(list(requests), "example.com")


# --- shape -> JSON Schema ---

def test_shape_becomes_a_typed_object_schema():
    schema = schema_from_shape(json.dumps({"sku": "string", "qty": "number", "active": "boolean"}))

    assert schema["type"] == "object"
    assert schema["properties"]["qty"] == {"type": "number"}
    assert sorted(schema["required"]) == ["active", "qty", "sku"]


def test_a_key_marked_optional_is_left_out_of_required():
    schema = schema_from_shape(json.dumps({"sku": "string", "note": "string?"}))

    assert schema["required"] == ["sku"]
    assert schema["properties"]["note"] == {"type": "string"}


def test_nested_objects_and_arrays_recurse():
    schema = schema_from_shape(json.dumps({"items": [{"id": "string"}]}))

    assert schema["properties"]["items"]["type"] == "array"
    assert schema["properties"]["items"]["items"]["properties"]["id"] == {"type": "string"}


def test_no_captured_shape_means_an_empty_schema_not_a_crash():
    """A form submit sends urlencoded data, so there is no JSON shape - an
    empty schema says "anything", which is the honest answer."""
    assert schema_from_shape("") == {}
    assert schema_from_shape("not json") == {}


# --- path templating ---

def test_repeated_id_segments_get_distinct_names():
    """`_pattern_and_params` collapses every opaque segment to {id};
    declaring the same parameter name twice is an invalid OpenAPI path."""
    templated, names = path_template("/orders/{id}/items/{id}")

    assert templated == "/orders/{orderId}/items/{itemId}"
    assert names == ["orderId", "itemId"]


def test_a_path_with_no_parameters_is_untouched():
    assert path_template("/rest/v1/orders") == ("/rest/v1/orders", [])


# --- document assembly ---

def test_generated_document_validates_against_openapi_31():
    document = _document(
        _request(method="POST", endpoint="api.example.com/orders",
                 body_shape=json.dumps({"sku": "string"}), status_codes=(201, 422)),
        _request(method="GET", endpoint="api.example.com/orders/{id}",
                 response_shape=json.dumps({"id": "string"})),
    )

    openapi_spec_validator.validate(document)


def test_only_observed_status_codes_appear():
    """A responses: block written from guesses is invention - 200 must not
    appear just because it usually does."""
    document = _document(_request(method="POST", status_codes=(201, 422)))

    responses = document["paths"]["/orders"]["post"]["responses"]

    assert sorted(responses) == ["201", "422"]


def test_an_endpoint_with_no_captured_status_says_so():
    document = _document(_request(status_codes=()))

    assert "default" in document["paths"]["/orders"]["get"]["responses"]


def test_identical_schemas_are_shared_through_a_ref():
    shape = json.dumps({"sku": "string"})
    document = _document(
        _request(method="POST", endpoint="api.example.com/orders", body_shape=shape, status_codes=(201,)),
        _request(method="PUT", endpoint="api.example.com/orders", body_shape=shape, status_codes=(200,)),
    )

    post_schema = document["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    put_schema = document["paths"]["/orders"]["put"]["requestBody"]["content"]["application/json"]["schema"]

    assert post_schema == put_schema
    assert post_schema["$ref"].startswith("#/components/schemas/")
    assert len(document["components"]["schemas"]) == 1


def test_operation_ids_follow_the_crud_mapping():
    document = _document(
        _request(method="POST", endpoint="api.example.com/orders", status_codes=(201,)),
        _request(method="DELETE", endpoint="api.example.com/orders", status_codes=(204,)),
        _request(method="GET", endpoint="api.example.com/orders", query_params=("status",)),
    )

    operations = document["paths"]["/orders"]

    assert operations["post"]["operationId"] == "createOrder"
    assert operations["delete"]["operationId"] == "deleteOrder"
    # GET with query params reads as a filtered listing, not a single fetch -
    # and a listing is the one case where the plural is correct.
    assert operations["get"]["operationId"] == "listOrders"


def test_where_an_endpoint_was_observed_is_written_into_the_description():
    """Traceability is the point: a reader who doubts an operation can go to
    the control it came from instead of taking the document's word."""
    document = _document(
        _request(method="POST", triggered_by=(("shop/cart", "div > button"),),
                 loaded_by=("shop/orders",), latencies_ms=(80, 120), status_codes=(201,))
    )

    description = document["paths"]["/orders"]["post"]["description"]

    assert "div > button" in description
    assert "shop/orders" in description
    assert "80-120 ms" in description


def test_several_hosts_get_per_path_servers():
    """One servers list for a crawl spanning two hosts would silently claim
    every path exists on both."""
    document = _document(
        _request(endpoint="api.example.com/orders"),
        _request(endpoint="auth.example.com/token"),
    )

    assert document["paths"]["/orders"]["servers"] == [{"url": "https://api.example.com"}]
    assert document["paths"]["/token"]["servers"] == [{"url": "https://auth.example.com"}]


def test_single_host_needs_no_per_path_servers():
    document = _document(_request(endpoint="api.example.com/orders"))

    assert "servers" not in document["paths"]["/orders"]
    assert document["servers"] == [{"url": "https://api.example.com"}]


def test_the_document_states_what_it_cannot_contain():
    """A contract that looks complete but isn't would be worse than one that
    says so.

    Rewritten deliberately when examples arrived: this used to assert
    "never their values", which encoded the design where nothing captured
    reached the document. Bodies are captured and redacted now, so the
    honest claim changed - what stays absent is field constraints, which
    need many values per field and would be guesses from one.
    """
    description = _document(_request())["info"]["description"]

    assert "Security schemes" in description
    assert "never what the token was" in description
    assert "Field constraints" in description


def test_an_empty_crawl_still_produces_a_valid_document():
    document = build_openapi_document([], "example.com")

    openapi_spec_validator.validate(document)
    assert document["paths"] == {}


def test_generate_produces_the_raw_overlay_and_public_triple():
    """docs/adr/0004's three-file split: openapi.raw.yaml (source),
    redaction.overlay.yaml (rule-catalog), openapi.yaml (public, also
    source) - all three parseable YAML, all three valid OpenAPI 3.1."""
    from generators.openapi import OpenAPIDocument

    class _Store:
        def get_inferred_requests(self):
            return [_request(method="POST", status_codes=(201,))]

    class _Request:
        graph_store = _Store()
        site = "example.com"
        settings: dict = {}

    outputs = OpenAPIDocument().generate(_Request())

    assert [o.filename for o in outputs] == ["openapi.raw", "redaction.overlay", "openapi"]
    assert [o.kind for o in outputs] == ["source", "rule-catalog", "source"]
    raw, overlay, public = (yaml.safe_load(o.content) for o in outputs)
    assert raw["openapi"] == "3.1.0"
    assert public["openapi"] == "3.1.0"
    assert overlay["overlay"] == "1.0.0"
    openapi_spec_validator.validate(raw)
    openapi_spec_validator.validate(public)


def test_every_operation_carries_x_inference():
    document = _document(_request(method="GET", endpoint="api.example.com/orders/{id}", status_codes=(200,)))

    inference = document["paths"]["/orders/{orderId}"]["get"]["x-inference"]

    assert inference["methods_observed"] == ["GET"]
    assert inference["methods_inferred"] == []
    assert 0.0 <= inference["confidence"]["path_params"] <= 1.0


def test_x_inference_confidence_scales_with_observation_count():
    low = _document(_request(method="POST", body_shape='{"sku": "string"}', status_codes=(201,),
                              observation_count=1))
    high = _document(_request(method="POST", body_shape='{"sku": "string"}', status_codes=(201,),
                               observation_count=10))

    low_confidence = low["paths"]["/orders"]["post"]["x-inference"]["confidence"]["request_schema"]
    high_confidence = high["paths"]["/orders"]["post"]["x-inference"]["confidence"]["request_schema"]

    assert low_confidence < high_confidence == 1.0


def test_x_inference_confidence_is_zero_without_any_captured_shape():
    document = _document(_request(method="POST", status_codes=(201,), observation_count=5))

    confidence = document["paths"]["/orders"]["post"]["x-inference"]["confidence"]

    assert confidence["request_schema"] == 0.0
    assert confidence["response_schema"] == 0.0


def test_path_params_confidence_is_certain_when_there_are_none():
    """No opaque segment was found - a verified structural fact, not a
    guess, so it needs no observation count to back it."""
    document = _document(_request(method="GET", endpoint="api.example.com/health", observation_count=0))

    assert document["paths"]["/health"]["get"]["x-inference"]["confidence"]["path_params"] == 1.0


def test_summary_is_a_phrase_not_a_restatement_of_the_operation_id():
    """It also must not print the raw {id} endpoint one line under a path
    key that reads {orderId} - the same parameter under two names."""
    document = _document(_request(method="POST", endpoint="api.example.com/orders/{id}/items",
                                  status_codes=(201,)))

    operation = document["paths"]["/orders/{orderId}/items"]["post"]

    assert operation["summary"] == "Create item"
    assert "{id}" not in operation["summary"]


# --- security schemes and media types (from captured headers) ---

def test_a_bearer_endpoint_declares_a_security_scheme():
    """Named from the header's scheme word - the token itself never left
    network_filter, so there is nothing here to leak."""
    document = _document(_request(method="POST", auth_schemes=("bearer",), status_codes=(201,)))

    assert document["components"]["securitySchemes"]["bearerAuth"] == {"type": "http", "scheme": "bearer"}
    assert document["paths"]["/orders"]["post"]["security"] == [{"bearerAuth": []}]
    openapi_spec_validator.validate(document)


def test_an_api_key_header_becomes_an_apikey_scheme_named_after_it():
    document = _document(_request(auth_schemes=("header:x-api-key",)))

    scheme = document["components"]["securitySchemes"]["xApiKey"]

    assert scheme == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    openapi_spec_validator.validate(document)


def test_a_cookie_becomes_a_cookie_scheme():
    document = _document(_request(auth_schemes=("cookie",)))

    assert document["components"]["securitySchemes"]["sessionCookie"]["in"] == "cookie"


def test_an_unrecognised_scheme_is_still_declared():
    """An unfamiliar Authorization scheme is still authentication - dropping
    it would tell a reader the endpoint is open."""
    document = _document(_request(auth_schemes=("negotiate",)))

    assert "negotiateAuth" in document["components"]["securitySchemes"]


def test_an_endpoint_with_no_observed_auth_declares_none():
    document = _document(_request())

    assert "securitySchemes" not in document.get("components", {})
    assert "security" not in document["paths"]["/orders"]["get"]


def test_the_observed_media_type_is_used_instead_of_assuming_json():
    document = _document(
        _request(method="GET", response_shape=json.dumps({"id": "string"}),
                 media_types=("application/xml",), status_codes=(200,))
    )

    assert list(document["paths"]["/orders"]["get"]["responses"]["200"]["content"]) == ["application/xml"]


def test_json_remains_the_fallback_when_no_media_type_was_captured():
    document = _document(
        _request(method="GET", response_shape=json.dumps({"id": "string"}), status_codes=(200,))
    )

    assert list(document["paths"]["/orders"]["get"]["responses"]["200"]["content"]) == ["application/json"]


def test_the_preamble_no_longer_claims_security_is_absent():
    """It was, until headers were read. What is still absent are examples
    and field constraints, and the preamble should say only that."""
    description = _document(_request())["info"]["description"]

    assert "Security schemes are named from request header names only" in description
    assert "never from a credential" in description


# --- examples: real bodies, redacted upstream ---

def test_a_request_body_example_reaches_the_operation():
    document = _document(_request(
        method="POST",
        body_shape='{"item": "string"}',
        request_example='{"item": "empanada"}',
        status_codes=(201,),
    ))

    body = document["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]
    assert body["example"] == '{"item": "empanada"}'


def test_a_response_example_lands_on_the_successful_status_only():
    document = _document(_request(
        method="POST",
        response_shape='{"id": "string"}',
        response_example='{"id": "abc"}',
        status_codes=(201, 422),
    ))

    responses = document["paths"]["/orders"]["post"]["responses"]
    assert responses["201"]["content"]["application/json"]["example"] == '{"id": "abc"}'
    assert "content" not in responses["422"]


def test_an_endpoint_with_no_captured_body_carries_no_example_key():
    """Absent, not empty-string: an example of "" would describe an endpoint
    that accepts an empty body."""
    document = _document(_request(method="POST", body_shape='{"item": "string"}', status_codes=(201,)))

    body = document["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]
    assert "example" not in body
