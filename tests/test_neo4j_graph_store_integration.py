"""Integration tests against a real Neo4j instance - skipped unless one is
reachable by any of three means (docs/explicativos/plan-almacenamiento.md
Fase C), tried in order:

1. An already-reachable instance via the usual env vars (NEO4J_HOST/PORT/...)
   - e.g. `docker compose up -d neo4j` run by hand first (see
   docker-compose.yml), or a shared CI service. Zero extra cost - this file's
   original, pre-Fase-C behavior, unchanged.
2. An ephemeral `testcontainers`-managed Neo4j container, started once for
   this test session and torn down at the end, when Docker is available but
   no instance is already up - `pip install testcontainers` (deliberately
   *not* the `testcontainers[neo4j]` extra: that extra hard-requires
   `neo4j>=6`, which would force-upgrade this project's pinned
   `neo4j==5.24.0` driver as a side effect of installing a test-only tool -
   see the plan doc's Fase C bitácora for the version conflict this was
   found to actually cause. Using testcontainers' generic `DockerContainer`
   instead means every actual query still goes through this project's own
   pinned `Neo4jGraphStore`/driver, identical to tier 1 - only *how the
   server got started* differs).
3. Skip - no Neo4j available by any means in this environment. Every
   individual test skips (not the whole module at collection time) so a
   plain `pytest --collect-only` never pays a container-startup cost just to
   list tests.
"""
import os
from typing import Any, Dict, Optional

import pytest

neo4j = pytest.importorskip("neo4j")

_TEST_SITE_CLEANUP_QUERIES = (
    "MATCH (p:Page {site: 'pragma-test.local'}) DETACH DELETE p",
    "MATCH (c:Component {site: 'pragma-test.local'}) DETACH DELETE c",
    "MATCH (t:TextContent {site: 'pragma-test.local'}) DETACH DELETE t",
    "MATCH (s:Site {name: 'pragma-test.local'}) DETACH DELETE s",
)


def _existing_instance_reachable() -> bool:
    """Tier 1 - the fast path, no container startup at all."""
    try:
        from src.storage.neo4j_graph_store import Neo4jGraphStore

        s = Neo4jGraphStore()
        s.connect()
        s.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def _neo4j_connection() -> Optional[Dict[str, Any]]:
    """Kwargs for `Neo4jGraphStore(**...)` for whichever tier resolved, or
    `None` if none did - session-scoped so an ephemeral container (tier 2)
    is started at most once per test run, not once per test function.
    """
    if _existing_instance_reachable():
        yield {
            "host": os.getenv("NEO4J_HOST", "localhost"),
            "port": int(os.getenv("NEO4J_PORT", "7687")),
            "user": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD"),
            "database": os.getenv("NEO4J_DATABASE", "neo4j"),
        }
        return

    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        yield None
        return

    password = "pragma-test-container"  # nosec - throwaway, ephemeral container, never persisted
    container = None
    try:
        # Constructing DockerContainer (not just .start()) can itself raise
        # docker.errors.DockerException - confirmed live while building this:
        # it eagerly talks to the Docker client, so "Docker installed but the
        # daemon isn't actually running" (a real state seen in this project's
        # own dev sandbox) fails right here, before .start() is ever reached.
        # Everything from construction through readiness must share one
        # try/except for tier 2 to degrade to tier 3 instead of erroring the
        # whole fixture.
        container = (
            DockerContainer("neo4j:5.24-community")  # same image pinned in docker-compose.yml
            .with_env("NEO4J_AUTH", f"neo4j/{password}")
            .with_exposed_ports(7687)
        )
        container.start()
        # "Bolt enabled on" is the Neo4j startup script's own readiness line
        # once the bolt listener is actually up - the same signal
        # testcontainers' own (unused here, see module docstring) Neo4j
        # module waits for.
        wait_for_logs(container, "Bolt enabled on", timeout=90)
    except Exception:
        # Docker installed but the daemon unreachable, image pull failed, or
        # the container never became ready in time - same end result as "no
        # Neo4j available" (tier 3), not a hard test failure.
        if container is not None:
            try:
                container.stop()
            except Exception:
                pass
        yield None
        return

    try:
        yield {
            "host": container.get_container_host_ip(),
            "port": int(container.get_exposed_port(7687)),
            "user": "neo4j",
            "password": password,
            "database": "neo4j",
        }
    finally:
        container.stop()


@pytest.fixture
def store(_neo4j_connection):
    if _neo4j_connection is None:
        pytest.skip(
            "No Neo4j available: not reachable via NEO4J_HOST/PORT, and testcontainers/Docker "
            "unavailable to start an ephemeral one. Run `docker compose up -d neo4j`, or install "
            "`testcontainers` with a running Docker daemon, to exercise this file."
        )

    from src.storage.neo4j_graph_store import Neo4jGraphStore

    s = Neo4jGraphStore(**_neo4j_connection)
    s.connect()
    # Clean slate for the test's site namespace so re-runs don't accumulate
    # (matters most for tier 1, a long-lived instance reused across runs -
    # a fresh tier-2 container has nothing to clean, but running the same
    # queries there is harmless).
    with s._session() as session:
        for query in _TEST_SITE_CLEANUP_QUERIES:
            session.run(query)
    yield s
    with s._session() as session:
        for query in _TEST_SITE_CLEANUP_QUERIES:
            session.run(query)
    s.close()


def test_constraint_setup_is_idempotent(store):
    store.connect()
    store.connect()  # must not raise on a second connect/constraint-creation


def test_upsert_page_creates_and_updates_single_node(store):
    site = "pragma-test.local"
    store.upsert_page(site, "x", status="Pending")
    store.upsert_page(site, "x", status="Finished", components=7)
    store.upsert_page(site, "x", status="Pending")  # must not revert Finished

    rows = store.get_progress_table_rows(site)
    assert len(rows) == 1
    assert rows[0]["status"] == "Finished"
    assert rows[0]["components"] == 7


def test_site_isolation_via_cypher(store):
    store.upsert_page("pragma-test.local", "shared", status="Finished")
    assert store.is_visited("pragma-test.local", "shared") is True
    assert store.is_visited("pragma-test-other.local", "shared") is False


def test_record_edge_and_get_edges_roundtrip(store):
    site = "pragma-test.local"
    store.record_edge(site, "home", "about", 'link "About"', "GOTO about")
    edges = store.get_edges(site)
    assert edges == [{"from": "home", "component": 'link "About"', "action": "GOTO about", "to": "about"}]


def test_link_label_is_scoped_to_the_specific_from_to_pair(store):
    site = "pragma-test.local"
    store.record_link(site, "home", "about", "About Us")
    store.record_link(site, "other-page", "about", "Learn more")

    assert store.get_link_label(site, "home", "about") == "About Us"
    assert store.get_link_label(site, "other-page", "about") == "Learn more"
    assert store.get_link_label(site, "unrelated-page", "about") is None


def test_clear_site_removes_pages_edges_and_links_but_not_other_sites(store):
    site, other = "pragma-test.local", "pragma-test-other.local"
    store.upsert_page(site, "home", status="Finished")
    store.record_edge(site, "home", "about", 'link "About"', "GOTO about")
    store.record_link(site, "home", "about", "About Us")
    store.upsert_page(other, "home", status="Finished")

    store.clear_site(site)

    assert store.get_progress_table_rows(site) == []
    assert store.get_edges(site) == []
    assert store.get_link_label(site, "home", "about") is None
    # A same-named page in a different site must survive - clear_site is
    # scoped, not a global wipe.
    assert store.is_visited(other, "home") is True


def test_record_component_is_idempotent_and_preserves_interacted(store):
    site = "pragma-test.local"
    store.record_component(site, "home", "button#go", tag="button", text="Go")
    store.record_component_interaction(site, "home", "button#go", action="click")
    store.record_component(site, "home", "button#go", tag="button", text="Go (updated)")

    states = store.get_component_states(site, "home")
    assert states["button#go"]["interacted"] is True
    assert states["button#go"]["text"] == "Go (updated)"


def test_record_component_persists_position(store):
    site = "pragma-test.local"
    store.record_component(
        site, "home", "button#go", tag="button", text="Go",
        x=10.0, y=20.0, width=80.0, height=32.0,
    )
    states = store.get_component_states(site, "home")
    assert states["button#go"]["x"] == 10.0
    assert states["button#go"]["height"] == 32.0

    ledger = store.get_component_ledger(site)
    assert ledger["home"]["button#go"]["width"] == 80.0


def test_record_component_persists_facts(store):
    from src.core.interfaces import ComponentFacts

    site = "pragma-test.local"
    facts = ComponentFacts(
        css_class="btn btn-primary", element_id="go-btn", href="",
        placeholder="", label="Go", name="", disabled=False, required=False, form="",
        color="rgb(255, 255, 255)", background_color="rgb(0, 100, 200)",
        font_size="16px", font_weight="700", display="inline-block", position="static",
    )
    store.record_component(site, "home", "button#go", tag="button", text="Go", facts=facts)

    state = store.get_component_states(site, "home")["button#go"]
    assert state["css_class"] == "btn btn-primary"
    assert state["element_id"] == "go-btn"
    assert state["color"] == "rgb(255, 255, 255)"

    ledger_entry = store.get_component_ledger(site)["home"]["button#go"]
    assert ledger_entry["background_color"] == "rgb(0, 100, 200)"

    # A ghost node auto-created via the interaction path (never went through
    # record_component's own `facts` param) must still get blank defaults for
    # every field, not a missing-key error when read back.
    store.record_component_interaction(site, "home", "button#never-inventoried", action="click")
    ghost_state = store.get_component_states(site, "home")["button#never-inventoried"]
    assert ghost_state["css_class"] == ""
    assert ghost_state["disabled"] is False


def test_record_component_type_and_options_roundtrip(store):
    import json

    site = "pragma-test.local"
    store.record_component(
        site, "home", "div#trigger", tag="div", text="Tercera Docena",
        component_type="custom control (component-library element, no native tag/role)",
    )
    options = json.dumps({
        "kind": "combobox_trigger",
        "choices": [{"text": "Mi Gusto", "selected": True}, {"text": "Solo Empanadas", "selected": False}],
    })
    store.record_component_options(site, "home", "div#trigger", options)

    states = store.get_component_states(site, "home")
    assert states["div#trigger"]["component_type"] == "custom control (component-library element, no native tag/role)"
    assert json.loads(states["div#trigger"]["options"])["choices"][0]["text"] == "Mi Gusto"

    # A later plain rediscovery (record_component has no `options` param at all)
    # must not clobber the options field back to empty - only
    # record_component_options does. component_type DOES refresh every call
    # (same discipline as x/y/width/height), so it's passed again here.
    store.record_component(
        site, "home", "div#trigger", tag="div", text="Tercera Docena (updated)",
        component_type="custom control (component-library element, no native tag/role)",
    )
    states = store.get_component_states(site, "home")
    assert states["div#trigger"]["options"] != ""
    assert states["div#trigger"]["component_type"] != ""

    ledger = store.get_component_ledger(site)
    assert ledger["home"]["div#trigger"]["component_type"] != ""


def test_record_component_interaction_auto_creates_node(store):
    site = "pragma-test.local"
    store.record_component_interaction(site, "home", "button#go", action="click", value="", resulting_url="about")

    states = store.get_component_states(site, "home")
    assert states["button#go"]["interacted"] is True

    ledger = store.get_component_ledger(site)
    assert ledger["home"]["button#go"]["interactions"] == [
        {"action": "click", "value": "", "resulting_url": "about"}
    ]


def test_count_unexplored_components_respects_semantic_only(store):
    site = "pragma-test.local"
    store.record_component(site, "home", "button#a", layer="semantic")
    store.record_component(site, "home", "div#b", layer="pointer")

    assert store.count_unexplored_components(site, semantic_only=True) == (1, 1)
    assert store.count_unexplored_components(site, semantic_only=False) == (2, 2)

    store.record_component_interaction(site, "home", "button#a", action="click")
    assert store.count_unexplored_components(site, semantic_only=True) == (0, 1)


def test_page_has_unexplored_components(store):
    site = "pragma-test.local"
    assert store.page_has_unexplored_components(site, "home") is False

    store.record_component(site, "home", "button#a")
    assert store.page_has_unexplored_components(site, "home") is True

    store.record_component_interaction(site, "home", "button#a", action="click")
    assert store.page_has_unexplored_components(site, "home") is False


def test_get_pages_with_unexplored_components_sorted_descending(store):
    site = "pragma-test.local"
    store.record_component(site, "x", "button#a")
    store.record_component(site, "y", "button#b")
    store.record_component(site, "y", "button#c")
    store.record_component(site, "z", "button#d")
    store.record_component_interaction(site, "z", "button#d", action="click")

    rows = store.get_pages_with_unexplored_components(site)
    assert rows == [
        {"url": "y", "unexplored_count": 2},
        {"url": "x", "unexplored_count": 1},
    ]


def test_clear_site_removes_components_too(store):
    site = "pragma-test.local"
    store.record_component(site, "home", "button#a")
    store.clear_site(site)

    assert store.get_component_states(site, "home") == {}
    assert store.count_unexplored_components(site) == (0, 0)
