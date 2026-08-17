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
        "MATCH (main:Container {landmark: 'main'})-[:CONTAINS]->(form:Container)-[:CONTAINS]->(c:Component) "
        "RETURN c.id",
    )
    assert row == [["https://x/y|button#go"]]


def test_contains_star_recovers_the_full_ancestor_chain(store) -> None:
    store.record_component_ancestors(
        "https://x/y",
        [{"path": "button#go", "ancestors": [_ancestor("main > form"), _ancestor("main", landmark="main")]}],
    )

    row = _rows(
        store,
        "MATCH (:Container {landmark: 'main'})-[:CONTAINS*1..8]->(c:Component) RETURN c.id",
    )
    assert row == [["https://x/y|button#go"]]


def test_two_components_sharing_an_ancestor_merge_onto_one_container_node(store) -> None:
    store.record_component_ancestors(
        "https://x/y",
        [
            {"path": "button#a", "ancestors": [_ancestor("nav", landmark="navigation")]},
            {"path": "button#b", "ancestors": [_ancestor("nav", landmark="navigation")]},
        ],
    )

    containers = _rows(store, "MATCH (n:Container) RETURN n.path")
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

    row = _rows(store, "MATCH (n:Container) RETURN n.tag, n.role, n.landmark, n.element_id, n.css_class")
    assert row == [["nav", "navigation", "navigation", "mainNav", "top"]]
