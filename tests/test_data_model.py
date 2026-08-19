"""Unit tests for the data model (generators/data_model.py) - pure functions
over hand-built ledger rows - plus the semantic tier's write path
(database/ladybug/semantic.py) against the real engine.
"""
from __future__ import annotations

import pytest

from core.interfaces import SemanticEntity, SemanticField
from database.ladybug.store import LadybugGraphStore
from generators.data_model import DataModelDocument, build_entities

PAGE = "https://shop.example/checkout"


@pytest.fixture
def store():
    instance = LadybugGraphStore("shop.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _input(path, name="email", input_type="text", form="#checkout", **extra):
    row = {
        "page_url": PAGE, "path": path, "tag": "input",
        "component_type": f"text field ({input_type})",
        "name": name, "label": "", "placeholder": "", "input_type": input_type,
        "required": False, "form": form, "interactions": [],
    }
    row.update(extra)
    return row


# --- derivation ---

def test_inputs_sharing_a_form_become_one_entity():
    entities = build_entities([_input("input#a", name="email"), _input("input#b", name="street")])

    assert len(entities) == 1
    assert [field.name for field in entities[0].fields] == ["email", "street"]


def test_the_entity_is_named_after_the_forms_own_id():
    entities = build_entities([_input("input#a", form="form#signup")])

    assert entities[0].name == "signup"


def test_a_form_with_no_id_falls_back_to_the_page():
    """Never a noun guessed from the fields: email+password could be a login,
    a signup or an invite, and this tier cannot show its work for that."""
    entities = build_entities([_input("input#a", form="div > form")])

    assert entities[0].name == "checkout form"


def test_two_forms_on_one_page_stay_two_entities():
    entities = build_entities([
        _input("input#a", form="#login"),
        _input("input#b", form="#newsletter"),
    ])

    assert sorted(entity.name for entity in entities) == ["login", "newsletter"]


def test_an_input_outside_any_form_is_not_an_entity():
    """A lone search box is not a thing the application collects."""
    assert build_entities([_input("input#q", form="")]) == []


def test_a_button_inside_a_form_is_not_a_field():
    rows = [
        _input("input#a"),
        {**_input("button#go"), "tag": "button", "component_type": "submit button"},
    ]

    assert [field.name for field in build_entities(rows)[0].fields] == ["email"]


def test_an_input_with_nothing_to_name_it_is_dropped_not_named_blank():
    assert build_entities([_input("input#a", name="", label="", placeholder="")]) == []


def test_the_declared_type_is_reported_never_corrected():
    """A field named for an email but declared text reads as a string here -
    D7 reports that gap, and silently fixing it would hide the finding."""
    entities = build_entities([_input("input#a", name="email", input_type="text")])

    assert entities[0].fields[0].data_type == "string"


def test_a_declared_type_maps_onto_the_semantic_vocabulary():
    entities = build_entities([
        _input("input#a", name="qty", input_type="number"),
        _input("input#b", name="agree", input_type="checkbox"),
        _input("input#c", name="born", input_type="date"),
    ])

    by_name = {field.name: field.data_type for field in entities[0].fields}
    assert by_name == {"agree": "boolean", "born": "date", "qty": "number"}


def test_validation_states_only_what_the_markup_declares():
    entities = build_entities([_input("input#a", input_type="email", required=True)])

    assert entities[0].fields[0].validation == "type=email, required"


def test_values_the_crawl_submitted_are_reported_as_evidence():
    entities = build_entities([_input("input#a", interactions=[
        {"action": "fill", "value": "test@example.com"},
        {"action": "click", "value": ""},
    ])])

    assert entities[0].fields[0].observed_values == ("test@example.com",)


def test_every_derived_node_carries_its_provenance():
    """The rule the whole tier rests on."""
    entities = build_entities([_input("input#a")])

    assert entities[0].derived_from == ((PAGE, "input#a"),)
    assert entities[0].fields[0].derived_from == ((PAGE, "input#a"),)


# --- the write path enforces provenance ---

def test_the_store_refuses_an_entity_with_no_provenance(store) -> None:
    """A comment saying "must carry DERIVED_FROM" is a rule a future writer
    breaks by accident. This is the one place it cannot be forgotten."""
    orphan = SemanticEntity(name="invented", description="", fields=(), derived_from=())

    with pytest.raises(ValueError, match="no derived_from"):
        store.record_entities([orphan])


def test_the_store_refuses_a_field_with_no_provenance(store) -> None:
    entity = SemanticEntity(
        name="checkout", description="", derived_from=((PAGE, "input#a"),),
        fields=(SemanticField(
            name="email", data_type="string", required=False, validation="",
            observed_values=(), derived_from=(),
        ),),
    )

    with pytest.raises(ValueError, match="no derived_from"):
        store.record_entities([entity])


def test_entities_round_trip_through_the_store(store) -> None:
    store.record_components(PAGE, [{"path": "input#a", "tag": "input", "text": ""}])
    original = build_entities([_input("input#a", name="email", input_type="email", required=True)])

    store.record_entities(original, run_id="run-1")

    assert store.get_entities() == original


def test_recording_entities_twice_is_a_full_rebuild(store) -> None:
    """A second run over a changed graph must not leave the first run's
    entities sitting next to the new ones."""
    store.record_entities(build_entities([_input("input#a", form="#old")]), run_id="run-1")
    store.record_entities(build_entities([_input("input#b", form="#new")]), run_id="run-2")

    assert [entity.name for entity in store.get_entities()] == ["new"]


def test_the_provenance_edge_records_which_run_and_generator(store) -> None:
    store.record_entities(build_entities([_input("input#a")]), run_id="run-7")

    rows = store._call(lambda conn: list(conn.execute(
        "MATCH (:Entity)-[d:DERIVED_FROM]->(:Component) RETURN d.run_id, d.generator, d.method"
    )))
    assert rows == [["run-7", "data_model.build_entities", "deterministic"]]


def test_a_field_edits_the_control_it_was_derived_from(store) -> None:
    """EDITS and DERIVED_FROM coincide today because the derivation is
    one-to-one, and are written separately because they answer different
    questions."""
    store.record_entities(build_entities([_input("input#a")]), run_id="run-1")

    rows = store._call(lambda conn: list(conn.execute(
        "MATCH (f:Field)-[:EDITS]->(c:Component) RETURN f.name, c.path"
    )))
    assert rows == [["email", "input#a"]]


# --- the document ---

def test_the_document_lists_each_form_with_its_evidence():
    class _Store:
        def get_component_ledger(self):
            return {PAGE: {"input#a": _input("input#a", input_type="email", required=True)}}

    class _Request:
        graph_store = _Store()
        site = "shop.example"

    text = DataModelDocument().generate(_Request())

    assert "## checkout" in text
    assert "type=email, required" in text
    assert "Derived from: `input#a`" in text


def test_a_crawl_with_no_forms_says_which_two_causes_are_open():
    class _Store:
        def get_component_ledger(self):
            return {}

    class _Request:
        graph_store = _Store()
        site = "shop.example"

    text = DataModelDocument().generate(_Request())

    assert "No forms with named inputs were found" in text
    assert "the two look the same here" in text
