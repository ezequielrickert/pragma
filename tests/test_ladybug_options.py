"""Regression tests for the Option write path - `database/ladybug/options.py`
(storage-migration plan step 8), exercised through `LadybugGraphStore`'s
public API against the real engine, same discipline as
`test_ladybug_network.py`. Read-side reconstruction
(`describe_options_from_rows`) is covered end-to-end via
`tests/test_component_tree.py` rather than duplicated here.
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


def test_choice_group_options_get_their_own_node_per_member(store) -> None:
    store.record_component_options(
        "https://x/y", "div#ship",
        {"group": "ship_method", "options": [
            {"path": "input#pickup", "text": "Pickup", "selected": False},
            {"path": "input#delivery", "text": "Home delivery", "selected": True},
        ]},
    )

    rows = _rows(
        store,
        """
        MATCH (:Component {id: $id})-[hop:HAS_OPTION]->(o:Option)
        RETURN o.path, o.text, o.selected, o.group_name, hop.seq ORDER BY hop.seq
        """,
        id="https://x/y|div#ship",
    )
    assert rows == [
        ["input#pickup", "Pickup", False, "ship_method", 0],
        ["input#delivery", "Home delivery", True, "ship_method", 1],
    ]


def test_revealed_options_carry_no_path(store) -> None:
    store.record_component_options(
        "https://x/y", "select#country",
        {"trigger": "select#country", "revealed_options": [
            {"text": "Argentina", "selected": False},
            {"text": "Uruguay", "selected": False},
        ]},
    )

    rows = _rows(store, "MATCH (:Component)-[:HAS_OPTION]->(o:Option) RETURN o.path, o.text")
    assert rows == [["", "Argentina"], ["", "Uruguay"]]


def test_stepper_encodes_its_four_roles_as_tagged_option_rows(store) -> None:
    store.record_component_options(
        "https://x/y", "div#qty",
        {"container": "div#qty", "increment_path": "button#plus", "decrement_path": "button#minus",
         "value_path": "span#qty-value", "current_value": "3"},
    )

    rows = _rows(
        store,
        "MATCH (:Component)-[:HAS_OPTION]->(o:Option) RETURN o.path, o.text, o.group_name ORDER BY o.text",
    )
    assert rows == [
        ["div#qty", "container", "stepper"],
        ["button#minus", "decrement", "stepper"],
        ["button#plus", "increment", "stepper"],
        ["span#qty-value", "value:3", "stepper"],
    ]


def test_rediscovery_replaces_the_option_set_rather_than_appending(store) -> None:
    """A stepper's current_value changes across passes - the old value
    row must not survive alongside the new one."""
    store.record_component_options(
        "https://x/y", "div#qty",
        {"increment_path": "button#plus", "decrement_path": "button#minus",
         "value_path": "span#qty-value", "current_value": "1"},
    )
    store.record_component_options(
        "https://x/y", "div#qty",
        {"increment_path": "button#plus", "decrement_path": "button#minus",
         "value_path": "span#qty-value", "current_value": "2"},
    )

    rows = _rows(store, "MATCH (:Component)-[:HAS_OPTION]->(o:Option) WHERE o.text STARTS WITH 'value' RETURN o.text")
    assert rows == [["value:2"]]


def test_options_can_be_recorded_before_the_component_row_exists(store) -> None:
    """_record_choice_group writes a representative's options before the
    batched record_components call gives it its descriptive fields -
    the write must not silently drop the options waiting for a Component
    node that doesn't exist yet."""
    store.record_component_options(
        "https://x/y", "div#ship",
        {"group": "ship_method", "options": [{"path": "input#pickup", "text": "Pickup", "selected": False}]},
    )

    row = _rows(store, "MATCH (c:Component {id: $id})-[:HAS_OPTION]->(:Option) RETURN c.path", id="https://x/y|div#ship")
    assert row == [["div#ship"]]


def test_an_unrecognized_options_shape_is_a_no_op(store) -> None:
    store.record_component_options("https://x/y", "div#mystery", {"unexpected": "shape"})

    assert _rows(store, "MATCH (:Option) RETURN count(*)") == [[0]]
