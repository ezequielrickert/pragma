"""Integration tests against a real Neo4j instance - skipped unless one is reachable.

Run `docker compose up -d neo4j` first (see docker-compose.yml). Not part of
the default fast test suite; CI/local runs without Neo4j simply skip this file.
"""
import pytest

neo4j = pytest.importorskip("neo4j")


def _neo4j_reachable() -> bool:
    try:
        from src.storage.neo4j_graph_store import Neo4jGraphStore

        store = Neo4jGraphStore()
        store.connect()
        store.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _neo4j_reachable(), reason="Neo4j not reachable at localhost:7687"
)


@pytest.fixture
def store():
    from src.storage.neo4j_graph_store import Neo4jGraphStore

    s = Neo4jGraphStore(database="neo4j")
    s.connect()
    # Clean slate for the test's site namespace so re-runs don't accumulate.
    with s._session() as session:
        session.run("MATCH (p:Page {site: 'pragma-test.local'}) DETACH DELETE p")
        session.run("MATCH (c:Component {site: 'pragma-test.local'}) DETACH DELETE c")
        session.run("MATCH (s:Site {name: 'pragma-test.local'}) DETACH DELETE s")
    yield s
    with s._session() as session:
        session.run("MATCH (p:Page {site: 'pragma-test.local'}) DETACH DELETE p")
        session.run("MATCH (c:Component {site: 'pragma-test.local'}) DETACH DELETE c")
        session.run("MATCH (s:Site {name: 'pragma-test.local'}) DETACH DELETE s")
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
