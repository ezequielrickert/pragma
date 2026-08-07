"""Tests for Module 3 (src/api_server) and its clients (src/scrapers/rest_scraper.py).

Three concerns: (1) catch drift between what the model is told exists (`TOOL_SPECS`'/`HELP_TOPICS`
in `src/core/interfaces.py`) and what Module 3 actually serves, in CI rather than at runtime;
(2) an in-process smoke test of both `/dynamic` and `/static` via FastAPI's `TestClient` (no real
subprocess/port needed, fast in CI); (3) `DocsClient`'s degrade-don't-raise contract.
"""
import pytest
from fastapi.testclient import TestClient

from src.api_server.app import app
from src.api_server.static_docs import TOPICS
from src.core.interfaces import HELP_TOPICS, TOOL_SPECS
from src.core.registry import SCRAPER_REGISTRY
from src.scrapers.rest_scraper import DocsClient, RestConfig


def test_dynamic_routes_cover_tool_specs():
    """Every model-facing browser action in TOOL_SPECS (except `finish`/`help`, which have no
    Playwright counterpart) must have a matching /dynamic/* route of the same name."""
    model_facing = {tool["name"] for tool in TOOL_SPECS} - {"finish", "help"}
    routes = {r.path for r in app.routes}
    missing = {name for name in model_facing if f"/dynamic/{name}" not in routes}
    assert not missing, f"No /dynamic/* route for TOOL_SPECS action(s): {missing}"


def test_help_topics_are_subset_of_static_docs():
    """HELP_TOPICS (what the model is told it can ask for) must all actually exist in
    Module 3's /static/* TOPICS - otherwise the model could ask for guidance that 404s."""
    missing = set(HELP_TOPICS) - set(TOPICS)
    assert not missing, f"HELP_TOPICS advertises topics Module 3 doesn't serve: {missing}"


def test_registries_populated_with_rest():
    assert "rest" in SCRAPER_REGISTRY.names()


def test_static_topics_endpoint_lists_all_topics():
    client = TestClient(app)
    response = client.get("/static/topics")
    assert response.status_code == 200
    listed = {row["topic"] for row in response.json()}
    assert listed == set(TOPICS)


def test_static_unknown_topic_is_404():
    client = TestClient(app)
    response = client.get("/static/not_a_real_topic")
    assert response.status_code == 404


@pytest.mark.network
def test_dynamic_navigate_smoke():
    """End-to-end smoke test: real Playwright navigation through the in-process app."""
    client = TestClient(app)
    response = client.post("/dynamic/navigate", json={"url": "https://www.iana.org/domains/example"})
    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://www.iana.org")

    state = client.get("/dynamic/state")
    assert state.status_code == 200
    assert state.json()["url"] == body["url"]


def test_docs_client_degrades_on_unreachable_server():
    """DocsClient.get() must not raise when Module 3 is unreachable - `help` should degrade
    to 'no extra guidance this turn', not abort the run."""
    client = DocsClient(RestConfig(base_url="http://127.0.0.1:1"))
    result = client.get("click_usage")
    assert "unavailable" in result


def test_components_state_reads_through_graph_store_runtime(monkeypatch):
    """GET /components/state must return whatever the underlying GraphStore's
    get_component_states reports, position included - it's a thin read-through, not
    its own storage. Uses an in-memory store as a stand-in for Neo4j so this test
    doesn't need a live database (see test_neo4j_graph_store_integration.py for that)."""
    from src.api_server import graph_store_runtime
    from src.storage.memory_graph_store import InMemoryGraphStore

    store = InMemoryGraphStore()
    store.record_component(
        "example.com", "example.com/x", "button#go",
        tag="button", text="Go", x=10.0, y=20.0, width=80.0, height=32.0,
    )
    monkeypatch.setattr(graph_store_runtime, "get_store", lambda: store)

    client = TestClient(app)
    response = client.get("/components/state", params={"site": "example.com", "page_url": "example.com/x"})
    assert response.status_code == 200
    body = response.json()
    assert body["button#go"]["interacted"] is False
    assert body["button#go"]["x"] == 10.0
    assert body["button#go"]["height"] == 32.0


def test_components_debt_reads_through_graph_store_runtime(monkeypatch):
    from src.api_server import graph_store_runtime
    from src.storage.memory_graph_store import InMemoryGraphStore

    store = InMemoryGraphStore()
    store.record_component("example.com", "example.com/x", "button#go")
    monkeypatch.setattr(graph_store_runtime, "get_store", lambda: store)

    client = TestClient(app)
    response = client.get("/components/debt", params={"site": "example.com"})
    assert response.status_code == 200
    assert response.json() == [{"url": "example.com/x", "unexplored_count": 1}]


def test_components_endpoints_503_when_graph_store_unreachable(monkeypatch):
    """A real Neo4j connection failure (e.g. graph_store: memory was used generator-side,
    or Neo4j just isn't reachable) must surface as a clear 503, not a bare 500 stack trace -
    this is the caller's signal that graph_store: neo4j is required for these routes."""
    from src.api_server import graph_store_runtime

    def _raise():
        raise RuntimeError("no password configured")

    monkeypatch.setattr(graph_store_runtime, "get_store", _raise)

    client = TestClient(app)
    response = client.get("/components/state", params={"site": "example.com", "page_url": "example.com/x"})
    assert response.status_code == 503
    assert "graph_store: neo4j" in response.json()["detail"]
