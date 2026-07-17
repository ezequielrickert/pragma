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
        session.run("MATCH (s:Site {name: 'pragma-test.local'}) DETACH DELETE s")
    yield s
    with s._session() as session:
        session.run("MATCH (p:Page {site: 'pragma-test.local'}) DETACH DELETE p")
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
