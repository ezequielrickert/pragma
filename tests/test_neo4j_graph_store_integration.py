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
    "MATCH (f:ComponentFamily {site: 'pragma-test.local'}) DETACH DELETE f",
    "MATCH (r:Request {site: 'pragma-test.local'}) DETACH DELETE r",
    "MATCH (rf:RequestFamily {site: 'pragma-test.local'}) DETACH DELETE rf",
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


def test_record_component_options_persists_clean_labels(store):
    site = "pragma-test.local"
    raw_json = '{"group": "flavor", "options": [{"text": "Mi Gusto", "selected": true}]}'
    store.record_component_options(
        site, "home", "combo#1", raw_json, option_labels=["Mi Gusto (selected)"]
    )

    state = store.get_component_states(site, "home")["combo#1"]
    assert state["options"] == raw_json
    assert state["option_labels"] == ["Mi Gusto (selected)"]

    ledger_entry = store.get_component_ledger(site)["home"]["combo#1"]
    assert ledger_entry["option_labels"] == ["Mi Gusto (selected)"]

    # No option_labels passed - a ghost node created via the interaction
    # auto-create path must still default it to [], not raise/omit the key.
    store.record_component_interaction(site, "home", "never-inventoried", action="click")
    ghost_state = store.get_component_states(site, "home")["never-inventoried"]
    assert ghost_state["option_labels"] == []


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
    # `source_path` is always present now, blank included: interactions live on
    # :INTERACTED relationships, where every property exists on every edge.
    assert ledger["home"]["button#go"]["interactions"] == [
        {"action": "click", "value": "", "resulting_url": "about", "source_path": "",
         "visit_id": "", "step_seq": 0}
    ]


def test_interactions_become_traversable_edges_to_the_resulting_page(store):
    """The point of the change: an interaction is an edge you can follow in
    the browser, not a JSON string buried in an array property."""
    site = "pragma-test.local"
    store.record_component_interaction(site, "home", "button#go", action="click", resulting_url="about")
    store.record_component_interaction(site, "home", "button#stay", action="click")

    with store._session() as session:
        rows = {
            r["path"]: r
            for r in session.run(
                """
                MATCH (c:Component {site: $site})-[i:INTERACTED]->(target:Page)
                RETURN c.path AS path, target.url AS target_url, i.navigated AS navigated, i.seq AS seq
                """,
                site=site,
            )
        }

    # A click that navigated points at where it landed...
    assert rows["button#go"]["target_url"] == "about"
    assert rows["button#go"]["navigated"] is True
    # ...one that didn't points back at its own page, so no interaction is
    # a dangling edge and every one is reachable from the page it happened on.
    assert rows["button#stay"]["target_url"] == "home"
    assert rows["button#stay"]["navigated"] is False


def test_repeated_interactions_keep_their_order(store):
    """`seq` is what replaces the old array's append order - without it the
    ledger could hand readers a component's interactions shuffled."""
    site = "pragma-test.local"
    for value in ("first", "second", "third"):
        store.record_component_interaction(site, "home", "input#q", action="fill", value=value)

    ledger = store.get_component_ledger(site)

    assert [i["value"] for i in ledger["home"]["input#q"]["interactions"]] == ["first", "second", "third"]


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


def test_apply_tag_labels_adds_a_dynamic_label_without_dropping_component(store):
    site = "pragma-test.local"
    store.record_component(site, "home", "button#a", tag="button")
    store.record_component(site, "home", "input#b", tag="input")

    store.apply_tag_labels(site, {"button": "Button", "input": "Input"})

    with store._session() as session:
        rows = {
            r["path"]: r["labels"]
            for r in session.run(
                "MATCH (c:Component {site: $site}) RETURN c.path AS path, labels(c) AS labels",
                site=site,
            )
        }
    assert set(rows["button#a"]) == {"Component", "Button"}
    assert set(rows["input#b"]) == {"Component", "Input"}


def test_record_component_families_roundtrips_and_replaces_on_rerun(store):
    from src.core.interfaces import ComponentFamily

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component(site, "home", "btn2", tag="button")

    families = [
        ComponentFamily(
            tag="button", component_type="button", common_classes=("btn", "btn-primary"),
            member_paths=(("home", "btn1"), ("home", "btn2")),
        )
    ]
    store.record_component_families(site, families)
    assert store.get_component_families(site) == families

    # A second, empty write must clear the first - a stale family from a
    # previous crawl must not linger once the data no longer supports it.
    store.record_component_families(site, [])
    assert store.get_component_families(site) == []


def test_record_component_families_persists_narrated_purpose(store):
    from src.core.interfaces import ComponentFamily

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component(site, "home", "btn2", tag="button")

    families = [
        ComponentFamily(
            tag="button", component_type="button", common_classes=("btn",),
            member_paths=(("home", "btn1"), ("home", "btn2")),
            purpose="Confirms or submits an action.",
        )
    ]
    store.record_component_families(site, families)
    assert store.get_component_families(site) == families
    assert store.get_component_families(site)[0].purpose == "Confirms or submits an action."


def test_record_inferred_requests_roundtrips_and_replaces_on_rerun(store):
    from src.core.interfaces import InferredRequest

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component(site, "home", "btn2", tag="button")

    requests = [
        InferredRequest(
            method="POST", endpoint="x.co/rest/v1/orders", query_params=("select",),
            body_shape='{"order_id": "string"}', response_shape='{"id": "string"}',
            triggered_by=(("home", "btn1"), ("home", "btn2")),
        )
    ]
    store.record_inferred_requests(site, requests)
    assert store.get_inferred_requests(site) == requests

    # A second, empty write must clear the first.
    store.record_inferred_requests(site, [])
    assert store.get_inferred_requests(site) == []


def test_inferred_requests_group_by_method_into_one_request_family(store):
    from src.core.interfaces import InferredRequest

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")

    requests = [
        InferredRequest(
            method="GET", endpoint="x.co/rest/v1/orders", query_params=(),
            body_shape="", response_shape="", triggered_by=(("home", "btn1"),),
        ),
        InferredRequest(
            method="GET", endpoint="x.co/rest/v1/flavors", query_params=(),
            body_shape="", response_shape="", triggered_by=(("home", "btn1"),),
        ),
    ]
    store.record_inferred_requests(site, requests)

    with store._session() as session:
        families = list(session.run(
            "MATCH (rf:RequestFamily {site: $site}) RETURN rf.method AS method", site=site
        ))
    assert len(families) == 1
    assert families[0]["method"] == "GET"


def test_clear_site_removes_component_families_too(store):
    from src.core.interfaces import ComponentFamily

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component_families(
        site,
        [ComponentFamily(tag="button", component_type="button", common_classes=(), member_paths=(("home", "btn1"),))],
    )
    store.clear_site(site)

    assert store.get_component_families(site) == []


def test_clear_site_removes_inferred_requests_too(store):
    from src.core.interfaces import InferredRequest

    site = "pragma-test.local"
    store.record_component(site, "home", "btn1", tag="button")
    store.record_inferred_requests(
        site,
        [InferredRequest(
            method="GET", endpoint="x.co/rest/v1/orders", query_params=(),
            body_shape="", response_shape="", triggered_by=(("home", "btn1"),),
        )],
    )
    store.clear_site(site)

    assert store.get_inferred_requests(site) == []


def test_nodes_carry_a_readable_caption(store):
    """Neo4j Browser picks a caption property on its own; left alone it lands
    on the CSS path. `caption` is what the .grass file points at."""
    site = "pragma-test.local"
    store.upsert_page(site, "shop/", title="Catalogo")
    store.record_component(site, "shop/", "div > button", tag="button", text="Comprar", component_type="button")
    store.record_component(site, "shop/", "div > input", tag="input", text="", component_type="text field (search)")

    with store._session() as session:
        captions = {
            r["path"]: r["caption"]
            for r in session.run(
                "MATCH (c:Component {site: $site}) RETURN c.path AS path, c.caption AS caption", site=site
            )
        }
        page_caption = session.run(
            "MATCH (p:Page {site: $site, url: 'shop/'}) RETURN p.caption AS caption", site=site
        ).single()["caption"]

    assert captions["div > button"] == "Comprar"
    # No visible text: falls back to the role, never to the CSS path.
    assert captions["div > input"] == "text field (search)"
    assert page_caption == "Catalogo"


def test_caption_does_not_clobber_the_dom_name_attribute(store):
    """`ComponentFacts.name` is the DOM `name` attribute and is persisted as
    `c.name`. An earlier revision called the caption `name` too and silently
    overwrote it - this is the regression guard."""
    from src.core.interfaces import ComponentFacts

    site = "pragma-test.local"
    store.record_component(
        site, "shop/", "div > input", tag="input", text="", component_type="text field (search)",
        facts=ComponentFacts(name="query"),
    )

    with store._session() as session:
        row = session.run(
            "MATCH (c:Component {site: $site, path: 'div > input'}) RETURN c.name AS name, c.caption AS caption",
            site=site,
        ).single()

    assert row["name"] == "query"
    assert row["caption"] == "text field (search)"


def test_inferred_nodes_are_labelled_apart_from_observed_ones(store):
    """Telling what the crawl saw from what the model deduced is both a
    legibility affordance and the precondition for auditing a deduction."""
    from src.core.interfaces import InferredRequest

    site = "pragma-test.local"
    store.record_component(site, "shop/", "div > button", tag="button", text="Comprar")
    store.record_inferred_requests(
        site,
        [InferredRequest(method="POST", endpoint="api/orders", query_params=(), body_shape="",
                         response_shape="", triggered_by=(("shop/", "div > button"),))],
    )

    with store._session() as session:
        inferred = {
            tuple(sorted(r["labels"]))
            for r in session.run(
                "MATCH (n:Inferred {site: $site}) RETURN labels(n) AS labels", site=site
            )
        }
        observed_is_not_inferred = session.run(
            "MATCH (c:Component {site: $site}) RETURN c:Inferred AS inferred", site=site
        ).single()["inferred"]

    assert ("Inferred", "Request") in inferred
    assert ("Inferred", "RequestFamily") in inferred
    assert observed_is_not_inferred is False


def test_page_load_requests_round_trip(store):
    """A SPA's route-entry fetches belong to the page, not to any component -
    without this they were never captured at all (plan H1)."""
    import json as _json

    site = "pragma-test.local"
    store.record_page_network(
        site, "shop/orders",
        _json.dumps([{"method": "GET", "url": "https://api/x/orders", "status": 200, "latency_ms": 42}]),
    )

    ledger = store.get_page_network_ledger(site)

    assert ledger == {
        "shop/orders": [{"method": "GET", "url": "https://api/x/orders", "status": 200, "latency_ms": 42}]
    }


def test_pages_with_no_load_requests_are_absent_from_the_ledger(store):
    site = "pragma-test.local"
    store.upsert_page(site, "shop/static", status="Finished")

    assert store.get_page_network_ledger(site) == {}


def test_inferred_request_persists_status_codes_and_load_attribution(store):
    from src.core.interfaces import InferredRequest

    site = "pragma-test.local"
    store.record_inferred_requests(
        site,
        [InferredRequest(
            method="POST", endpoint="api/orders", query_params=(), body_shape="",
            response_shape="", triggered_by=(), loaded_by=("shop/",),
            status_codes=(201, 422), latencies_ms=(80, 120),
        )],
    )

    read_back = store.get_inferred_requests(site)[0]

    assert read_back.status_codes == (201, 422)
    assert read_back.latencies_ms == (80, 120)
    assert read_back.loaded_by == ("shop/",)


def test_an_interaction_carries_the_position_it_happened_at(store):
    """A scenario is a sequence; the graph recorded facts with no ordering
    between components until visit_id/step_seq were stamped on."""
    from src.core.interfaces import VisitStep

    site = "pragma-test.local"
    step = VisitStep(visit_id="visit-abc")
    store.record_component_interaction(site, "home", "input#q", action="fill", value="x", step=step.take())
    store.record_component_interaction(site, "home", "button#go", action="click", step=step.take())

    ledger = store.get_component_ledger(site)["home"]

    assert ledger["input#q"]["interactions"][0]["visit_id"] == "visit-abc"
    assert ledger["input#q"]["interactions"][0]["step_seq"] == 1
    assert ledger["button#go"]["interactions"][0]["step_seq"] == 2


def test_an_unstamped_interaction_reads_back_as_unordered_not_missing(store):
    """Every write path that predates traces still works, and its
    interactions are distinguishable from ordered ones by seq 0."""
    site = "pragma-test.local"
    store.record_component_interaction(site, "home", "button#go", action="click")

    interaction = store.get_component_ledger(site)["home"]["button#go"]["interactions"][0]

    assert interaction["visit_id"] == ""
    assert interaction["step_seq"] == 0


def test_page_metadata_round_trips(store):
    """Meta tags were extracted on every navigation and thrown away every
    time - the page's own account of what it is."""
    import json as _json

    site = "pragma-test.local"
    store.record_page_metadata(site, "home", _json.dumps({"description": "Una tienda", "og:type": "website"}))

    assert store.get_page_metadata(site) == {"home": {"description": "Una tienda", "og:type": "website"}}


def test_the_ledger_returns_the_layer_a_filter_depends_on(store):
    """accessibility.undersized_targets excludes the cursor:pointer
    discovery net by reading `layer`. It was recorded and never returned,
    so that filter silently never fired on real data."""
    site = "pragma-test.local"
    store.record_component(site, "home", "div#x", tag="div", role="button", input_type="", layer="pointer")

    record = store.get_component_ledger(site)["home"]["div#x"]

    assert record["layer"] == "pointer"
    assert record["role"] == "button"
