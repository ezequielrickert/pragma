"""Regression tests for the Container/CONTAINS write path -
`database/ladybug/containment.py` (storage-migration plan step 8),
exercised through `LadybugGraphStore`'s public API against the real
engine, same discipline as `test_ladybug_network.py`.
"""
from __future__ import annotations

import pytest

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


def _ancestor(path, tag="div", role="", landmark="", element_id="", css_class=""):
    return {"path": path, "tag": tag, "role": role, "landmark": landmark, "id": element_id, "class": css_class}


def test_direct_containment_only_no_closure_row(store) -> None:
    """Two ancestors deep: exactly two direct CONTAINS edges, no shortcut
    edge from the outer container straight to the component."""
    store.record_component_ancestors(
        "https://x/y",
        [{"path": "button#go", "ancestors": [_ancestor("main > form"), _ancestor("main", landmark="main")]}],
    )

    direct = _rows(store, "MATCH ()-[:CONTAINS]->() RETURN count(*)")
    assert direct == [[2]]

    row = _rows(
        store,
        """
        MATCH (main:Container {landmark: 'main'})-[:CONTAINS]->(form:Container)-[:CONTAINS]->(c:Component)
        MATCH (:Page {url: 'https://x/y'})-[e:HAS_COMPONENT]->(c)
        RETURN e.path
        """,
    )
    assert row == [["button#go"]]


def test_contains_star_recovers_the_full_ancestor_chain(store) -> None:
    store.record_component_ancestors(
        "https://x/y",
        [{"path": "button#go", "ancestors": [_ancestor("main > form"), _ancestor("main", landmark="main")]}],
    )

    row = _rows(
        store,
        """
        MATCH (:Container {landmark: 'main'})-[:CONTAINS*1..8]->(c:Component)
        MATCH (:Page {url: 'https://x/y'})-[e:HAS_COMPONENT]->(c)
        RETURN e.path
        """,
    )
    assert row == [["button#go"]]


def test_two_components_sharing_an_ancestor_merge_onto_one_container_node(store) -> None:
    # Distinct text keeps the two leaf components themselves distinct -
    # only the shared ancestor is expected to collapse here.
    store.record_components(
        "https://x/y", [{"path": "button#a", "text": "A"}, {"path": "button#b", "text": "B"}],
    )
    store.record_component_ancestors(
        "https://x/y",
        [
            {"path": "button#a", "ancestors": [_ancestor("nav", landmark="navigation")]},
            {"path": "button#b", "ancestors": [_ancestor("nav", landmark="navigation")]},
        ],
    )

    containers = _rows(store, "MATCH (:Page)-[e:HAS_CONTAINER]->(:Container) RETURN e.path")
    edges = _rows(store, "MATCH (:Container)-[:CONTAINS]->(:Component) RETURN count(*)")
    assert containers == [["nav"]]
    assert edges == [[2]]


def test_a_component_with_no_ancestors_creates_nothing(store) -> None:
    store.record_component_ancestors("https://x/y", [{"path": "button#go", "ancestors": []}])

    assert _rows(store, "MATCH (n:Container) RETURN count(*)") == [[0]]


def test_container_descriptive_fields_are_captured(store) -> None:
    store.record_component_ancestors(
        "https://x/y",
        [{"path": "button#go", "ancestors": [
            _ancestor("nav", tag="nav", role="navigation", landmark="navigation", element_id="mainNav", css_class="top")
        ]}],
    )

    row = _rows(store, "MATCH (n:Container) RETURN n.tag, n.role, n.landmark, n.css_class")
    assert row == [["nav", "navigation", "navigation", "top"]]

    edge_row = _rows(store, "MATCH (:Page)-[e:HAS_CONTAINER]->(:Container) RETURN e.path, e.element_id")
    assert edge_row == [["nav", "mainNav"]]


# --- the read path: which landmark region a component sits in ---

_REGION_PAGE = "https://x/shop"


def _page_with_regions(store: LadybugGraphStore) -> None:
    """A button inside <form> inside <main>, a search box inside a <nav>
    that is itself inside that <main>, and a link inside no landmark."""
    store.upsert_page(_REGION_PAGE, status="Finished")
    store.record_components(_REGION_PAGE, [
        {"path": "button#buy", "tag": "button", "text": "Comprar"},
        {"path": "input#q", "tag": "input", "text": ""},
        {"path": "a#logo", "tag": "a", "text": "Inicio"},
    ])
    store.record_component_ancestors(_REGION_PAGE, [
        {"path": "button#buy", "ancestors": [
            _ancestor("form#cart", tag="form"),
            _ancestor("main", tag="main", landmark="main"),
        ]},
        {"path": "input#q", "ancestors": [
            _ancestor("nav", tag="nav", landmark="navigation"),
            _ancestor("main", tag="main", landmark="main"),
        ]},
        {"path": "a#logo", "ancestors": [_ancestor("div#wrap")]},
    ])


def test_get_component_regions_reports_the_nearest_landmark(store) -> None:
    """A nav nested inside main reports navigation, not main: the inner
    region is the one a reader would name."""
    _page_with_regions(store)

    regions = store.get_component_regions()

    assert regions[_REGION_PAGE]["button#buy"] == "main"
    assert regions[_REGION_PAGE]["input#q"] == "navigation"


def test_get_component_regions_omits_a_component_in_no_landmark(store) -> None:
    """Absent, not present-with-empty-string: a missing key cannot be
    mistaken for a region genuinely named ""."""
    _page_with_regions(store)

    assert "a#logo" not in store.get_component_regions()[_REGION_PAGE]


def test_get_component_regions_is_empty_without_recorded_ancestry(store) -> None:
    """What a crawl from before containment capture reads back as."""
    store.upsert_page(_REGION_PAGE, status="Finished")
    store.record_components(_REGION_PAGE, [{"path": "button#buy", "tag": "button", "text": "x"}])

    assert store.get_component_regions() == {}
