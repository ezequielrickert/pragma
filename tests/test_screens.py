"""Unit tests for the Screen derivation (generators/screens.py) - pure
functions over hand-built page rows - plus the semantic tier's Screen
write path (database/ladybug/screen.py) against the real engine.
"""
from __future__ import annotations

import pytest

from core.interfaces import SemanticEntity, SemanticField, SemanticScreen
from database.ladybug.store import LadybugGraphStore
from generators.data_model import build_entities
from generators.screens import build_screens

SITE = "screens.example"


@pytest.fixture
def store():
    instance = LadybugGraphStore(SITE)
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _page(url, status="Finished", components=0):
    return {"url": url, "status": status, "components": components}


# --- derivation ---


def test_one_screen_per_finished_page():
    screens = build_screens([_page("shop.example/checkout"), _page("shop.example/cart")])
    assert [s.page_url for s in screens] == ["shop.example/cart", "shop.example/checkout"]


def test_a_pending_page_gets_no_screen():
    screens = build_screens([_page("shop.example/checkout"), _page("shop.example/never-visited", status="Pending")])
    assert [s.page_url for s in screens] == ["shop.example/checkout"]


def test_route_pattern_is_the_base_route_shape():
    screens = build_screens([_page("shop.example/product/abcdef0123456789")])
    assert screens[0].route_pattern == "shop.example/product/{token}"


def test_a_state_toggle_page_stays_a_distinct_screen_sharing_one_route_pattern():
    screens = build_screens([
        _page("shop.example/map"),
        _page("shop.example/map#state:9f8e7d6c5b4a"),
    ])
    assert len(screens) == 2
    assert screens[0].page_url != screens[1].page_url
    assert screens[0].route_pattern == screens[1].route_pattern == "shop.example/map"


def test_a_freshly_built_screen_carries_no_name_or_purpose():
    screens = build_screens([_page("shop.example/checkout")])
    assert screens[0].name == ""
    assert screens[0].purpose == ""


# --- store write path ---


def test_the_store_refuses_a_screen_with_no_page_url(store) -> None:
    orphan = SemanticScreen(page_url="", route_pattern="shop.example/checkout")
    with pytest.raises(ValueError):
        store.record_screens([orphan])


def test_screens_round_trip_through_the_store(store) -> None:
    original = build_screens([_page("shop.example/checkout")])
    store.record_screens(original, run_id="run-1")
    assert store.get_screens() == original


def test_recording_screens_twice_is_a_full_rebuild(store) -> None:
    store.record_screens(build_screens([_page("shop.example/old")]), run_id="run-1")
    store.record_screens(build_screens([_page("shop.example/new")]), run_id="run-2")
    assert [s.page_url for s in store.get_screens()] == ["shop.example/new"]


def test_a_screen_renders_its_page(store) -> None:
    store.record_screens(build_screens([_page("shop.example/checkout")]), run_id="run-1")

    def op(conn):
        return list(conn.execute(
            "MATCH (s:Screen)-[:RENDERS]->(p:Page) RETURN p.url"
        ))

    rows = store._call(op)
    assert rows == [["shop.example/checkout"]]


def test_recording_screens_does_not_wipe_entity_provenance(store) -> None:
    """DERIVED_FROM is a rel table both record_entities and record_screens
    write into - a blanket delete in either would erase the other's
    provenance depending on call order."""
    entity = SemanticEntity(
        name="checkout", description="d",
        fields=(SemanticField(
            name="email", data_type="email", required=True, validation="",
            observed_values=(), derived_from=(("shop.example/checkout", "#a"),),
        ),),
        derived_from=(("shop.example/checkout", "#a"),),
    )
    store.record_entities([entity], run_id="run-1")
    store.record_screens(build_screens([_page("shop.example/checkout")]), run_id="run-1")

    assert [e.name for e in store.get_entities()] == ["checkout"]


def test_recording_entities_does_not_wipe_screen_provenance(store) -> None:
    store.record_screens(build_screens([_page("shop.example/checkout")]), run_id="run-1")
    store.record_entities(build_entities([]), run_id="run-1")

    assert [s.page_url for s in store.get_screens()] == ["shop.example/checkout"]


def test_the_provenance_edge_records_which_run_and_generator(store) -> None:
    store.record_screens(build_screens([_page("shop.example/checkout")]), run_id="run-7")

    def op(conn):
        return list(conn.execute(
            "MATCH (:Screen)-[e:DERIVED_FROM]->(:Page) RETURN e.run_id, e.generator, e.method, e.confidence"
        ))

    rows = store._call(op)
    assert rows == [["run-7", "screens.build_screens", "deterministic", 1.0]]
