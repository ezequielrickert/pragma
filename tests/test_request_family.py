"""Unit tests for request_family.py's pure endpoint-inference logic."""
import json

from generators.request_family import (
    build_inferred_requests,
    normalized_endpoint,
    query_param_names,
)


def _comp(page_url, path, requests):
    return {"page_url": page_url, "path": path, "network_requests": requests}


def _req(method="POST", url="https://x.co/rest/v1/orders", body_shape="", response_shape=""):
    return {"method": method, "url": url, "body_shape": body_shape, "response_shape": response_shape}


def test_normalized_endpoint_collapses_opaque_path_segments():
    url = "https://x.supabase.co/rest/v1/orders/8d206b72-b0c9-48d9-a265-7043f93139aa/items"
    assert normalized_endpoint(url) == "x.supabase.co/rest/v1/orders/{id}/items"


def test_normalized_endpoint_keeps_real_words():
    assert normalized_endpoint("https://x.co/rest/v1/participant_selections") == "x.co/rest/v1/participant_selections"


def test_query_param_names_sorted_without_values():
    url = "https://x.co/rest/v1/orders?select=*&order_id=eq.8d206b72-b0c9-48d9-a265-7043f93139aa"
    assert query_param_names(url) == ("order_id", "select")
    assert "8d206b72" not in str(query_param_names(url))


def test_two_components_calling_the_same_endpoint_merge_into_one_request():
    components = [
        _comp("p1", "btn1", [_req(url="https://x.co/rest/v1/participant_selections?select=*")]),
        _comp("p1", "btn2", [_req(url="https://x.co/rest/v1/participant_selections?select=*")]),
    ]
    requests = build_inferred_requests(components)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert set(requests[0].triggered_by) == {("p1", "btn1"), ("p1", "btn2")}


def test_different_methods_to_the_same_path_never_merge():
    components = [
        _comp("p1", "btn1", [_req(method="GET", url="https://x.co/rest/v1/orders")]),
        _comp("p1", "btn2", [_req(method="POST", url="https://x.co/rest/v1/orders")]),
    ]
    requests = build_inferred_requests(components)
    assert len(requests) == 2
    assert {r.method for r in requests} == {"GET", "POST"}


def test_different_query_params_never_merge():
    components = [
        _comp("p1", "btn1", [_req(url="https://x.co/rest/v1/orders?select=*")]),
        _comp("p1", "btn2", [_req(url="https://x.co/rest/v1/orders?select=*&order_id=eq.abc")]),
    ]
    requests = build_inferred_requests(components)
    assert len(requests) == 2


def test_body_and_response_shape_carried_from_first_non_empty_occurrence():
    components = [
        _comp("p1", "btn1", [_req(url="https://x.co/rest/v1/orders", body_shape="")]),
        _comp("p1", "btn2", [_req(url="https://x.co/rest/v1/orders", body_shape='{"order_id": "string"}')]),
    ]
    requests = build_inferred_requests(components)
    assert requests[0].body_shape == '{"order_id": "string"}'


def test_component_with_no_network_requests_contributes_nothing():
    components = [_comp("p1", "btn1", [])]
    assert build_inferred_requests(components) == []


def test_component_missing_page_url_or_path_is_skipped_not_errored():
    components = [{"page_url": None, "path": "btn1", "network_requests": [_req()]}]
    assert build_inferred_requests(components) == []


def test_request_with_no_method_or_url_is_skipped():
    components = [_comp("p1", "btn1", [{"method": "", "url": "", "body_shape": "", "response_shape": ""}])]
    assert build_inferred_requests(components) == []


def test_result_is_sorted_deterministically():
    components = [
        _comp("p1", "btn1", [_req(method="POST", url="https://x.co/b")]),
        _comp("p1", "btn2", [_req(method="GET", url="https://x.co/a")]),
    ]
    requests = build_inferred_requests(components)
    assert [(r.method, r.endpoint) for r in requests] == [("GET", "x.co/a"), ("POST", "x.co/b")]


def _request(url, method="GET", **extra):
    return {"method": method, "url": url, "body_shape": "", "response_shape": "", **extra}


def test_page_load_requests_are_attributed_to_the_page_not_a_component():
    """A SPA fetches what it needs to render on route entry, with no
    component to blame. Folding those into triggered_by with a blank path
    would claim a control exists that doesn't."""
    inferred = build_inferred_requests(
        [], {"shop/orders": [_request("https://api/x/orders", status=200)]}
    )

    assert len(inferred) == 1
    assert inferred[0].loaded_by == ("shop/orders",)
    assert inferred[0].triggered_by == ()


def test_one_endpoint_can_be_both_loaded_and_triggered():
    component = {
        "page_url": "shop/orders", "path": "div > button",
        "network_requests": [_request("https://api/x/orders", method="POST")],
    }
    inferred = build_inferred_requests(
        [component], {"shop/orders": [_request("https://api/x/orders")]}
    )

    by_method = {r.method: r for r in inferred}
    assert by_method["GET"].loaded_by == ("shop/orders",)
    assert by_method["POST"].triggered_by == (("shop/orders", "div > button"),)


def test_status_codes_and_latencies_are_collected_across_samples():
    """An OpenAPI responses: block built without real status codes is
    invention - this is where they come from."""
    component = {
        "page_url": "p", "path": "b",
        "network_requests": [
            _request("https://api/x/orders", method="POST", status=201, latency_ms=120),
            _request("https://api/x/orders", method="POST", status=422, latency_ms=80),
            _request("https://api/x/orders", method="POST", status=201, latency_ms=95),
        ],
    }

    inferred = build_inferred_requests([component])[0]

    assert inferred.status_codes == (201, 422)
    assert inferred.latencies_ms == (80, 95, 120)


def test_a_key_missing_from_some_samples_is_marked_optional():
    """"First non-empty shape wins" made every OpenAPI property required by
    accident. A key absent from some calls is optional by observation."""
    component = {
        "page_url": "p", "path": "b",
        "network_requests": [
            _request("https://api/x/orders", method="POST",
                     body_shape=json.dumps({"sku": "string", "note": "string"})),
            _request("https://api/x/orders", method="POST",
                     body_shape=json.dumps({"sku": "string"})),
        ],
    }

    shape = json.loads(build_inferred_requests([component])[0].body_shape)

    assert shape["sku"] == "string"
    assert shape["note"] == "string?"


def test_identical_shapes_across_samples_stay_unmarked():
    component = {
        "page_url": "p", "path": "b",
        "network_requests": [
            _request("https://api/x/orders", method="POST", body_shape=json.dumps({"sku": "string"})),
            _request("https://api/x/orders", method="POST", body_shape=json.dumps({"sku": "string"})),
        ],
    }

    assert json.loads(build_inferred_requests([component])[0].body_shape) == {"sku": "string"}
