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
