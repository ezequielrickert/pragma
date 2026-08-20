"""Accessibility-snapshot write+read path against the real engine -
database/ladybug/accessibility_snapshot.py.
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


def test_a_captured_snapshot_round_trips(store) -> None:
    store.upsert_page(PAGE, status="Finished")

    store.record_accessibility_snapshot(PAGE, 'heading "Welcome"\n', '{"nodes": []}')

    assert store.get_accessibility_snapshots() == {
        PAGE: {"aria_snapshot_yaml": 'heading "Welcome"\n', "axtree_json": '{"nodes": []}'},
    }


def test_a_page_not_yet_written_still_lands(store) -> None:
    """MERGE, not MATCH - the same reason record_state_styles MERGEs its
    Component: a page whose upsert_page has not landed yet must not
    silently drop this."""
    store.record_accessibility_snapshot(PAGE, 'button "Buy"\n', '{"nodes": []}')

    assert PAGE in store.get_accessibility_snapshots()


def test_a_page_with_neither_field_is_not_stored(store) -> None:
    store.upsert_page(PAGE, status="Finished")

    store.record_accessibility_snapshot(PAGE, "", "")

    assert store.get_accessibility_snapshots() == {}


def test_nothing_captured_reads_back_empty(store) -> None:
    store.upsert_page(PAGE, status="Finished")

    assert store.get_accessibility_snapshots() == {}
