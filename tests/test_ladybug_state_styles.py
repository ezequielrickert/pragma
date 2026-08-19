"""StateStyle/HAS_STATE_STYLE write+read path against the real engine -
database/ladybug/state_styles.py.
"""
from __future__ import annotations

import pytest

from database.ladybug.store import LadybugGraphStore

PAGE = "https://x/shop"


@pytest.fixture
def store():
    instance = LadybugGraphStore("test.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _entry(path="button#buy", **states):
    return {"path": path, "states": states or {"hover": {"color": "#1a4f9c"}}}


def test_declared_states_round_trip(store) -> None:
    store.upsert_page(PAGE, status="Finished")
    store.record_components(PAGE, [{"path": "button#buy", "tag": "button", "text": "Comprar"}])

    store.record_state_styles(PAGE, [_entry(hover={"color": "#1a4f9c", "opacity": "0.9"})])

    assert store.get_state_styles() == [
        {"page_url": PAGE, "path": "button#buy", "state": "hover",
         "property": "color", "value": "#1a4f9c"},
        {"page_url": PAGE, "path": "button#buy", "state": "hover",
         "property": "opacity", "value": "0.9"},
    ]


def test_hover_and_focus_are_stored_separately(store) -> None:
    store.upsert_page(PAGE, status="Finished")
    store.record_components(PAGE, [{"path": "a#x", "tag": "a", "text": "Ir"}])

    store.record_state_styles(PAGE, [
        _entry("a#x", hover={"color": "#111"}, focus={"outline": "2px solid #fc0"}),
    ])

    assert {row["state"] for row in store.get_state_styles()} == {"focus", "hover"}


def test_a_rediscovery_overwrites_rather_than_duplicating(store) -> None:
    """Keyed by (component, state, property): a hover colour that changed
    between runs reports the new value with no stale row beside it."""
    store.upsert_page(PAGE, status="Finished")
    store.record_components(PAGE, [{"path": "button#buy", "tag": "button", "text": "Comprar"}])

    store.record_state_styles(PAGE, [_entry(hover={"color": "#old"})])
    store.record_state_styles(PAGE, [_entry(hover={"color": "#new"})])

    rows = store.get_state_styles()
    assert len(rows) == 1
    assert rows[0]["value"] == "#new"


def test_a_style_for_a_component_not_yet_written_still_lands(store) -> None:
    """MERGE, not MATCH - a MATCH that matches nothing drops the whole pattern
    silently, so write order would decide whether styles survive."""
    store.upsert_page(PAGE, status="Finished")

    store.record_state_styles(PAGE, [_entry("button#ghost")])

    assert [row["path"] for row in store.get_state_styles()] == ["button#ghost"]


def test_an_empty_value_is_not_stored(store) -> None:
    store.upsert_page(PAGE, status="Finished")

    store.record_state_styles(PAGE, [_entry(hover={"color": ""})])

    assert store.get_state_styles() == []


def test_nothing_recorded_reads_back_empty(store) -> None:
    assert store.get_state_styles() == []
