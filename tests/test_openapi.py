"""Unit tests for the OpenAPI document (src/generators/openapi.py and
json_schema.py). Fully deterministic - no model, no browser, no store."""
import json

import pytest
import yaml

from src.core.interfaces import InferredRequest
from src.generators.json_schema import schema_from_shape
from src.generators.openapi import build_openapi_document, path_template

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
    """normalized_endpoint collapses every opaque segment to {id}; declaring
    the same parameter name twice is an invalid OpenAPI path."""
    templated, names = path_template("/orders/{id}/items/{id}")

    assert templated == "/orders/{orderId}/items/{itemId}"
    assert names == ["orderId", "itemId"]


def test_a_path_with_no_parameters_is_untouched():
    assert path_template("/rest/v1/orders") == ("/rest/v1/orders", [])


# --- document assembly ---

def test_generated_document_validates_against_openapi_30():
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
    """Absent security schemes are a privacy decision, not an oversight -
    a contract that looks complete but isn't would be worse than one that
    says so."""
    description = _document(_request())["info"]["description"]

    assert "Security schemes" in description
    assert "never their values" in description


def test_an_empty_crawl_still_produces_a_valid_document():
    document = build_openapi_document([], "example.com")

    openapi_spec_validator.validate(document)
    assert document["paths"] == {}


def test_output_is_parseable_yaml():
    from src.generators.openapi import OpenAPIDocument

    class _Store:
        def get_inferred_requests(self, site):
            return [_request(method="POST", status_codes=(201,))]

    class _Request:
        graph_store = _Store()
        site = "example.com"

    text = OpenAPIDocument().generate(_Request())

    assert yaml.safe_load(text)["openapi"] == "3.0.3"


def test_summary_is_a_phrase_not_a_restatement_of_the_operation_id():
    """It also must not print the raw {id} endpoint one line under a path
    key that reads {orderId} - the same parameter under two names."""
    document = _document(_request(method="POST", endpoint="api.example.com/orders/{id}/items",
                                  status_codes=(201,)))

    operation = document["paths"]["/orders/{orderId}/items"]["post"]

    assert operation["summary"] == "Create item"
    assert "{id}" not in operation["summary"]
