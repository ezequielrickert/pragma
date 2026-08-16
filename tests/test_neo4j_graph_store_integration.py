"""Neo4j-specific integration tests: everything here inspects a real driver
session, raw Cypher, or a Neo4j-only concept (dynamic tag labels, the
`:Inferred` marker, Browser captions) - the reason it can't live in
`test_graph_store_conformance.py`, which only calls `GraphStore`'s own
public methods so it stays valid for every backend at once.

Skipped unless a Neo4j instance is reachable - see
`graph_store_backends._resolve_neo4j_connection` for the three-tier
resolution (existing instance / ephemeral testcontainers instance / skip)
this file shares with the conformance suite.
"""
import pytest

neo4j = pytest.importorskip("neo4j")

from tests.graph_store_backends import resolve_neo4j_connection  # noqa: E402


@pytest.fixture
def store():
    kwargs = resolve_neo4j_connection()
    if kwargs is None:
        pytest.skip(
            "No Neo4j available: not reachable via NEO4J_HOST/PORT, and testcontainers/Docker "
            "unavailable to start an ephemeral one. Run `docker compose up -d neo4j`, or install "
            "`testcontainers` with a running Docker daemon, to exercise this file."
        )

    from database.neo4j_graph_store import Neo4jGraphStore

    site = "pragma-neo4j-test.local"
    s = Neo4jGraphStore(**kwargs)
    s.connect()
    s.clear_site(site)
    yield s
    s.clear_site(site)
    s.close()


def test_constraint_setup_is_idempotent(store):
    store.connect()
    store.connect()  # must not raise on a second connect/constraint-creation


def test_interactions_become_traversable_edges_to_the_resulting_page(store):
    """The point of storing interactions as edges rather than a JSON array
    property: an interaction is something you can follow in the browser."""
    site = "pragma-neo4j-test.local"
    store.record_component_interaction(site, "home", "button#go", action="click", resulting_url="about")
    store.record_component_interaction(site, "home", "button#stay", action="click")

    with store._session() as session:
        rows = {
            r["path"]: r
            for r in session.run(
                """
                MATCH (c:Component {site: $site})-[i:INTERACTED]->(target:Page)
                RETURN c.path AS path, target.url AS target_url, i.navigated AS navigated
                """,
                site=site,
            )
        }

    # A click that navigated points at where it landed...
    assert rows["button#go"]["target_url"] == "about"
    assert rows["button#go"]["navigated"] is True
    # ...one that didn't points back at its own page, so no interaction is a
    # dangling edge and every one is reachable from the page it happened on.
    assert rows["button#stay"]["target_url"] == "home"
    assert rows["button#stay"]["navigated"] is False


def test_apply_tag_labels_adds_a_dynamic_label_without_dropping_component(store):
    site = "pragma-neo4j-test.local"
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


def test_inferred_requests_group_by_method_into_one_request_family(store):
    from core.interfaces import InferredRequest

    site = "pragma-neo4j-test.local"
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


def test_nodes_carry_a_readable_caption(store):
    """Neo4j Browser picks a caption property on its own; left alone it lands
    on the CSS path. `caption` is what the .grass file points at."""
    site = "pragma-neo4j-test.local"
    store.upsert_page(site, "shop/", title="Catalog")
    store.record_component(site, "shop/", "div > button", tag="button", text="Buy", component_type="button")
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

    assert captions["div > button"] == "Buy"
    # No visible text: falls back to the role, never to the CSS path.
    assert captions["div > input"] == "text field (search)"
    assert page_caption == "Catalog"


def test_caption_does_not_clobber_the_dom_name_attribute(store):
    """`ComponentFacts.name` is the DOM `name` attribute, persisted as
    `c.name`. An earlier revision called the caption `name` too and silently
    overwrote it - this is the regression guard."""
    from core.interfaces import ComponentFacts

    site = "pragma-neo4j-test.local"
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
    from core.interfaces import InferredRequest

    site = "pragma-neo4j-test.local"
    store.record_component(site, "shop/", "div > button", tag="button", text="Buy")
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
