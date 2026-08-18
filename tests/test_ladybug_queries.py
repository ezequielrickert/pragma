"""Regression tests for the retrieval surface - `database/ladybug/queries.py`
(storage-migration plan step 9), exercised through `LadybugGraphStore`'s
public API against the real engine, same discipline as
`test_ladybug_network.py`.
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


# --- raw() guard ---

def test_raw_runs_a_genuine_read(store) -> None:
    store.upsert_page("https://x/y", status="Finished", title="Home")

    rows = store.raw("MATCH (p:Page {url: $url}) RETURN p.title", {"url": "https://x/y"})

    assert rows == [["Home"]]


@pytest.mark.parametrize("cypher", [
    "CREATE (:Page {url: 'evil'})",
    "MATCH (p:Page) SET p.title = 'hijacked'",
    "MATCH (p:Page) DETACH DELETE p",
    "DROP TABLE Page",
    "MATCH (p:Page) RETURN p.title; CREATE (:Page {url: 'evil'})",
    "",
    "   ",
    "CALL CREATE_FTS_INDEX('Page', 'x', ['title'])",
])
def test_raw_rejects_write_shapes(store, cypher) -> None:
    with pytest.raises(ValueError):
        store.raw(cypher)


def test_raw_allows_a_read_shaped_call(store) -> None:
    """A CALL to a non-mutating procedure (unlike CREATE_FTS_INDEX above)
    must not be rejected just for using the CALL keyword."""
    store.ensure_search_indexes()
    store.upsert_page("https://x/y", status="Finished", description="checkout for orders")

    rows = store.raw(
        'CALL QUERY_FTS_INDEX("Page", "page_description_fts", $q) RETURN node.url',
        {"q": "orders"},
    )
    assert rows == [["https://x/y"]]


def test_raw_truncates_to_the_limit_not_the_query_text(store) -> None:
    for i in range(5):
        store.upsert_page(f"https://x/{i}", status="Finished")

    rows = store.raw("MATCH (p:Page) RETURN p.url ORDER BY p.url", limit=2)

    assert len(rows) == 2


def test_raw_does_not_leak_its_timeout_into_the_next_call(store) -> None:
    """set_query_timeout is a connection-wide setting on the one shared
    writer connection - raw() must reset it, not leave a later ordinary
    write timing out because an earlier raw() call set a short one."""
    store.raw("MATCH (p:Page) RETURN p.url", timeout_s=1)

    store.upsert_page("https://x/y", status="Finished")  # must not raise/hang

    assert store.is_visited("https://x/y") is True


# --- schema_card ---

def test_schema_card_names_every_observation_table(store) -> None:
    card = store.schema_card()

    for table in ("Page", "Component", "Interaction", "Request", "Endpoint", "Payload"):
        assert f"NODE TABLE IF NOT EXISTS {table}(" in card
    assert "--" not in card, "Ladybug rejects inline SQL comments in execute() - none may survive here"


# --- named queries ---

def test_endpoint_contract_aggregates_across_observations(store) -> None:
    store.record_page_network(
        "https://x/y",
        [
            {"method": "GET", "host": "x", "path": "/orders", "query_params": [], "resource_type": "fetch",
             "status": 200, "status_text": "", "failed": False, "failure_text": None,
             "body_shape": "", "response_shape": "", "request_body_excerpt": "", "request_body_length": 0,
             "request_body_hash": "", "response_body_excerpt": "", "response_body_length": 0,
             "response_body_hash": "", "latency_ms": None, "media_type": "application/json",
             "auth_scheme": "bearer", "is_first_party": True},
            {"method": "GET", "host": "x", "path": "/orders", "query_params": [], "resource_type": "fetch",
             "status": 500, "status_text": "", "failed": False, "failure_text": None,
             "body_shape": "", "response_shape": "", "request_body_excerpt": "", "request_body_length": 0,
             "request_body_hash": "", "response_body_excerpt": "", "response_body_length": 0,
             "response_body_hash": "", "latency_ms": None, "media_type": "application/json",
             "auth_scheme": "bearer", "is_first_party": True},
        ],
    )

    contract = store.endpoint_contract("GET x/orders")

    assert contract["status_codes"] == [200, 500]
    assert contract["call_count"] == 2
    assert contract["first_party"] is True


def test_endpoint_contract_returns_none_for_an_unknown_endpoint(store) -> None:
    assert store.endpoint_contract("GET nowhere/x") is None


def test_callers_of_reports_the_triggering_component(store) -> None:
    store.record_component("https://x/y", "button#go", tag="button")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("https://x/y", "button#go", "click", step=step)
    store.record_component_network(
        "https://x/y", "button#go",
        [{"method": "POST", "host": "x", "path": "/orders", "query_params": [], "resource_type": "fetch",
          "status": 201, "status_text": "", "failed": False, "failure_text": None,
          "body_shape": "", "response_shape": "", "request_body_excerpt": "", "request_body_length": 0,
          "request_body_hash": "", "response_body_excerpt": "", "response_body_length": 0,
          "response_body_hash": "", "latency_ms": None, "media_type": "", "auth_scheme": "",
          "visit_id": "v1", "step_seq": 1, "is_first_party": True}],
    )

    callers = store.callers_of("POST x/orders")

    assert callers == [{"page_url": "https://x/y", "path": "button#go"}]


def test_integrations_lists_only_third_party_endpoints(store) -> None:
    store.record_page_network(
        "https://x/y",
        [{"method": "GET", "host": "www.google-analytics.com", "path": "/collect", "query_params": [],
          "resource_type": "fetch", "status": 200, "status_text": "", "failed": False, "failure_text": None,
          "body_shape": "", "response_shape": "", "request_body_excerpt": "", "request_body_length": 0,
          "request_body_hash": "", "response_body_excerpt": "", "response_body_length": 0,
          "response_body_hash": "", "latency_ms": None, "media_type": "", "auth_scheme": "",
          "is_first_party": False}],
    )

    integrations = store.integrations()

    assert integrations == [
        {"host": "www.google-analytics.com", "method": "GET", "path_pattern": "/collect", "call_count": 1}
    ]


def test_flows_from_recovers_multi_hop_reachability(store) -> None:
    store.record_edge("https://x/a", "https://x/b", "a#next", "click")
    store.record_edge("https://x/b", "https://x/c", "a#next", "click")

    reachable = store.flows_from("https://x/a", max_hops=2)

    assert reachable == ["https://x/b", "https://x/c"]


def test_components_in_recovers_nested_containment(store) -> None:
    store.record_component_ancestors(
        "https://x/y",
        [{"path": "button#go", "ancestors": [
            {"path": "main > form", "tag": "form", "role": "", "landmark": "", "id": "", "class": ""},
            {"path": "main", "tag": "main", "role": "", "landmark": "main", "id": "", "class": ""},
        ]}],
    )

    members = store.components_in("https://x/y|main")

    assert members == [{"id": "https://x/y|button#go", "path": "button#go"}]


def test_unexplored_is_a_parity_shim_for_get_pending(store) -> None:
    store.upsert_page("https://x/y", status="Pending")

    assert store.unexplored() == store.get_pending()


# --- query() dispatcher ---

def test_query_dispatches_by_name(store) -> None:
    store.upsert_page("https://x/y", status="Pending")

    assert store.query("unexplored") == store.get_pending()


def test_query_dispatches_with_kwargs(store) -> None:
    store.record_edge("https://x/a", "https://x/b", "a#next", "click")

    assert store.query("flows_from", page_url="https://x/a", max_hops=1) == ["https://x/b"]


@pytest.mark.parametrize("name", ["_call", "raw", "query", "not_a_real_method"])
def test_query_refuses_private_and_disallowed_names(store, name) -> None:
    with pytest.raises(ValueError):
        store.query(name)
