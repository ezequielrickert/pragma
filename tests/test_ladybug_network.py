"""Regression tests for the API-contract write/read path -
`database/ladybug/network.py` (storage-migration plan step 7), exercised
through `LadybugGraphStore`'s public API against the real engine, same
discipline as `test_ladybug_observation.py`/`test_ladybug_read_path.py`.
"""
from __future__ import annotations

import pytest

from core.interfaces import VisitStep
from database.ladybug.store import LadybugGraphStore


@pytest.fixture
def store():
    instance = LadybugGraphStore("test.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _rows(store: LadybugGraphStore, query: str, **params):
    return list(store._call(lambda conn: list(conn.execute(query, params))))


def _request(**overrides):
    base = {
        "method": "GET", "host": "x.supabase.co", "path": "/rest/v1/orders",
        "query_params": ["select"], "resource_type": "fetch",
        "status": 200, "status_text": "OK", "failed": False, "failure_text": None,
        "body_shape": "", "response_shape": "",
        "request_body_excerpt": "", "request_body_length": 0, "request_body_hash": "",
        "response_body_excerpt": "", "response_body_length": 0, "response_body_hash": "",
        "latency_ms": 42, "media_type": "application/json", "auth_scheme": "bearer",
        "is_first_party": True,
    }
    base.update(overrides)
    return base


def test_page_load_request_creates_a_request_node_loaded_from_its_page(store) -> None:
    store.record_page_network("https://x/y", [_request()])

    row = _rows(
        store,
        "MATCH (:Page {url: $url})-[:LOADED]->(r:Request) RETURN r.method, r.path, r.status",
        url="https://x/y",
    )
    assert row == [["GET", "/rest/v1/orders", 200]]


def test_page_load_request_merges_onto_an_endpoint_with_call_count(store) -> None:
    store.record_page_network("https://x/y", [_request()])

    row = _rows(
        store,
        "MATCH (:Request)-[:CALLS]->(e:Endpoint) RETURN e.id, e.method, e.host, e.path_pattern, "
        "e.first_party, e.call_count",
    )
    assert row == [["GET x.supabase.co/rest/v1/orders", "GET", "x.supabase.co", "/rest/v1/orders", True, 1]]


def test_two_observations_of_the_same_endpoint_shape_merge_and_increment_call_count(store) -> None:
    """Two different order ids collapse onto one Endpoint - the {id}
    collapsing heuristic doing its job at write time, not a rebuild pass."""
    store.record_page_network("https://x/y", [_request(path="/orders/8d206b72-aaaa-bbbb-cccc")])
    store.record_page_network("https://x/y", [_request(path="/orders/f91a3c04-dddd-eeee-ffff")])

    row = _rows(store, "MATCH (e:Endpoint) RETURN e.path_pattern, e.path_params, e.call_count")
    assert row == [["/orders/{id}", ["id"], 2]]


def test_third_party_request_creates_no_request_node_only_bumps_the_endpoint(store) -> None:
    store.record_page_network(
        "https://x/y",
        [_request(host="www.google-analytics.com", path="/collect", is_first_party=False)],
    )

    requests = _rows(store, "MATCH (r:Request) RETURN r.method")
    endpoints = _rows(store, "MATCH (e:Endpoint) RETURN e.host, e.first_party, e.call_count")
    assert requests == []
    assert endpoints == [["www.google-analytics.com", False, 1]]


def test_component_triggered_request_hangs_off_the_matching_interaction(store) -> None:
    store.record_component("https://x/y", "button#go", tag="button")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("https://x/y", "button#go", "click", step=step)

    store.record_component_network(
        "https://x/y", "button#go",
        [{**_request(method="POST", path="/orders"), "visit_id": "v1", "step_seq": 1}],
    )

    row = _rows(
        store,
        """
        MATCH (:Component {id: $id})-[:PERFORMED]->(:Interaction)-[:TRIGGERED]->(r:Request)
        RETURN r.method, r.path
        """,
        id="https://x/y|button#go",
    )
    assert row == [["POST", "/orders"]]


def test_component_network_request_with_no_matching_interaction_step_is_skipped(store) -> None:
    """A request missing visit_id/step_seq names no interaction to
    attribute to - skipped, not a crash and not an orphaned Request."""
    store.record_component("https://x/y", "button#go", tag="button")

    store.record_component_network("https://x/y", "button#go", [_request()])

    assert _rows(store, "MATCH (r:Request) RETURN r.method") == []


def test_request_and_response_bodies_attach_via_has_body_with_direction(store) -> None:
    store.record_page_network(
        "https://x/y",
        [_request(
            request_body_hash="abc", request_body_excerpt='{"order_id":"1"}', request_body_length=17,
            response_body_hash="def", response_body_excerpt='{"id":"2"}', response_body_length=10,
        )],
    )

    rows = _rows(
        store,
        "MATCH (:Request)-[h:HAS_BODY]->(p:Payload) RETURN h.direction, p.hash, p.byte_length ORDER BY h.direction",
    )
    assert rows == [["request", "abc", 17], ["response", "def", 10]]


def test_two_requests_sharing_a_response_body_dedupe_onto_one_payload(store) -> None:
    store.record_page_network("https://x/y", [_request(response_body_hash="same", response_body_length=5)])
    store.record_page_network("https://x/y", [_request(response_body_hash="same", response_body_length=5)])

    assert _rows(store, "MATCH (p:Payload) RETURN count(p)") == [[1]]
    assert _rows(store, "MATCH ()-[:HAS_BODY {direction: 'response'}]->(:Payload) RETURN count(*)") == [[2]]


def test_get_inferred_requests_aggregates_status_codes_and_query_params_across_observations(store) -> None:
    store.record_page_network(
        "https://x/y",
        [
            _request(status=200, query_params=["select"]),
            _request(status=500, query_params=["order_id"]),
        ],
    )

    requests = store.get_inferred_requests()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.endpoint == "x.supabase.co/rest/v1/orders"
    assert request.status_codes == (200, 500)
    assert request.query_params == ("order_id", "select")
    assert request.loaded_by == ("https://x/y",)


def test_get_inferred_requests_reports_the_triggering_component(store) -> None:
    store.record_component("https://x/y", "button#go", tag="button")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("https://x/y", "button#go", "click", step=step)
    store.record_component_network(
        "https://x/y", "button#go", [{**_request(method="POST", path="/orders"), "visit_id": "v1", "step_seq": 1}],
    )

    requests = store.get_inferred_requests()

    assert requests[0].triggered_by == (("https://x/y", "button#go"),)
    assert requests[0].loaded_by == ()


def test_get_inferred_requests_excludes_third_party_endpoints(store) -> None:
    """This method answers "what is this application's own API" - see
    `Endpoint`'s own schema comment for the asymmetric retention behind
    third-party traffic never earning a `Request` node at all."""
    store.record_page_network(
        "https://x/y",
        [_request(host="www.google-analytics.com", path="/collect", is_first_party=False)],
    )

    assert store.get_inferred_requests() == []


# --- captured bodies as contract examples ---

def test_a_captured_request_body_reaches_the_inferred_contract(store) -> None:
    store.record_page_network("https://x/y", [_request(
        method="POST", request_body_excerpt='{"item":"empanada"}',
        request_body_hash="h1", request_body_length=19, status=201,
    )])

    assert store.get_inferred_requests()[0].request_example == '{"item":"empanada"}'


def test_a_response_body_from_a_failed_call_is_not_offered_as_the_example(store) -> None:
    """A 422's body describes the error shape. Publishing it as the
    endpoint's response example would misdescribe the happy path."""
    store.record_page_network("https://x/y", [_request(
        method="POST", response_body_excerpt='{"error":"invalid"}',
        response_body_hash="bad", response_body_length=19, status=422,
    )])

    assert store.get_inferred_requests()[0].response_example == ""


def test_the_successful_body_wins_when_both_were_observed(store) -> None:
    store.record_page_network("https://x/y", [_request(
        method="POST", response_body_excerpt='{"error":"invalid"}',
        response_body_hash="bad", response_body_length=19, status=422,
    )])
    store.record_page_network("https://x/y", [_request(
        method="POST", response_body_excerpt='{"id":"ok"}',
        response_body_hash="good", response_body_length=11, status=201,
    )])

    assert store.get_inferred_requests()[0].response_example == '{"id":"ok"}'


def test_the_shortest_observed_body_is_the_example(store) -> None:
    """Deterministic across runs, and keeps a truncated 8KB blob from being
    the example when a small body was also seen."""
    store.record_page_network("https://x/y", [_request(
        method="POST", request_body_excerpt='{"item":"a really long body here"}',
        request_body_hash="long", request_body_length=33, status=201,
    )])
    store.record_page_network("https://x/y", [_request(
        method="POST", request_body_excerpt='{"item":"x"}',
        request_body_hash="short", request_body_length=12, status=201,
    )])

    assert store.get_inferred_requests()[0].request_example == '{"item":"x"}'


def test_an_endpoint_with_no_captured_bodies_reports_empty_examples(store) -> None:
    store.record_page_network("https://x/y", [_request()])

    contract = store.get_inferred_requests()[0]
    assert (contract.request_example, contract.response_example) == ("", "")
