"""Unit tests for the Rule derivation (generators/rules.py) - pure
functions over hand-built ledger rows - plus the semantic tier's Rule
write path (database/ladybug/rule.py) against the real engine.
"""
from __future__ import annotations

import pytest

from core.interfaces import SemanticEntity, SemanticField, SemanticRule
from database.ladybug.store import LadybugGraphStore
from generators.data_model import build_entities
from generators.rules import build_rules

PAGE = "https://shop.example/checkout"


def _input(path, name="email", input_type="text", form="#checkout", tag="input", **extra):
    row = {
        "page_url": PAGE, "path": path, "tag": tag,
        "component_type": f"text field ({input_type})",
        "name": name, "label": "", "placeholder": "", "input_type": input_type,
        "required": False, "form": form,
    }
    row.update(extra)
    return row


def _select(path, name="country", form="#checkout", choices=(), selected_index=None):
    """A `<select>` whose `HAS_OPTION` rows carry real DOM `path`s -
    `choice_group`, the only shape `_option_set_statement` reads."""
    rows = [
        {"path": f"{path} > option:nth-child({i + 1})", "text": text, "selected": i == selected_index}
        for i, text in enumerate(choices)
    ]
    return {
        "page_url": PAGE, "path": path, "tag": "select",
        "component_type": "select", "name": name, "label": "", "placeholder": "",
        "input_type": "", "required": False, "form": form,
        "options": (rows, "country-group"),
    }


# --- derivation: declared constraints ---


def test_a_field_with_no_declared_constraint_gets_no_rule():
    assert build_rules([_input("input#a")]) == []


def test_required_becomes_its_own_rule():
    rules = build_rules([_input("input#a", required=True)])
    assert [r.statement for r in rules] == ["required"]


def test_a_non_text_type_becomes_its_own_rule():
    rules = build_rules([_input("input#a", input_type="email")])
    assert [r.statement for r in rules] == ["type=email"]


def test_a_plain_text_type_is_not_reported_as_a_constraint():
    rules = build_rules([_input("input#a", input_type="text")])
    assert rules == []


def test_each_numeric_length_pattern_attribute_becomes_its_own_rule():
    rules = build_rules([_input(
        "input#a", input_type="number",
        pattern="^[0-9]+$", min="1", max="10", minlength="1", maxlength="2", step="1",
    )])

    statements = sorted(r.statement for r in rules)
    assert statements == [
        "max=10", "maxlength=2", "min=1", "minlength=1", "pattern=^[0-9]+$", "step=1", "type=number",
    ]


def test_every_rule_carries_its_source_component_as_derived_from():
    rules = build_rules([_input("input#a", required=True)])
    assert rules[0].derived_from == (PAGE, "input#a")


def test_every_rule_is_declared_with_full_confidence():
    rules = build_rules([_input("input#a", required=True)])
    assert rules[0].kind == "declared"
    assert rules[0].confidence == 1.0


def test_a_component_outside_a_form_yields_no_rule():
    assert build_rules([_input("input#a", form="", required=True)]) == []


def test_a_non_field_component_yields_no_rule():
    button = {**_input("button#go"), "tag": "button", "component_type": "submit button", "required": True}
    assert build_rules([button]) == []


# --- derivation: <select> option sets ---


def test_a_select_with_declared_choices_gets_one_option_set_rule():
    rules = build_rules([_select("select#country", choices=("AR", "BR", "CL"))])
    assert [r.statement for r in rules] == ["one of: [AR, BR, CL]"]


def test_the_option_set_statement_does_not_mark_which_choice_is_selected():
    rules = build_rules([_select("select#country", choices=("AR", "BR"), selected_index=0)])
    assert rules[0].statement == "one of: [AR, BR]"


def test_a_select_with_no_captured_options_yields_no_option_set_rule():
    """A native <select>'s own <option> children are not discovered as
    components at all today - see rules.py's own docstring."""
    rules = build_rules([_select("select#country", choices=())])
    assert rules == []


def test_a_non_select_tag_never_yields_an_option_set_rule_even_with_option_rows():
    component = _input("div#menu", tag="div", component_type="dropdown")
    component["options"] = ([{"path": "li#a", "text": "AR", "selected": False}], "menu-group")
    assert build_rules([component]) == []


# --- ordering ---


def test_rules_are_sorted_by_source_then_statement():
    rules = build_rules([
        _input("input#b", required=True),
        _input("input#a", required=True),
    ])
    assert [r.derived_from for r in rules] == [(PAGE, "input#a"), (PAGE, "input#b")]


# --- store write path ---


@pytest.fixture
def store():
    instance = LadybugGraphStore("rules.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def test_the_store_refuses_a_rule_with_no_derived_from(store) -> None:
    orphan = SemanticRule(statement="required", kind="declared", confidence=1.0, derived_from=())
    with pytest.raises(ValueError, match="no derived_from"):
        store.record_rules([orphan])


def test_rules_round_trip_through_the_store(store) -> None:
    store.record_components(PAGE, [{"path": "input#a", "tag": "input", "text": ""}])
    original = build_rules([_input("input#a", required=True)])

    store.record_rules(original, run_id="run-1")

    assert store.get_rules() == original


def test_recording_rules_twice_is_a_full_rebuild(store) -> None:
    store.record_rules(build_rules([_input("input#a", form="#old", required=True)]), run_id="run-1")
    store.record_rules(build_rules([_input("input#b", form="#new", required=True)]), run_id="run-2")

    assert [r.derived_from for r in store.get_rules()] == [(PAGE, "input#b")]


def test_the_provenance_edge_records_which_run_and_generator(store) -> None:
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-7")

    rows = store._call(lambda conn: list(conn.execute(
        "MATCH (:Rule)-[d:DERIVED_FROM]->(:Component) RETURN d.run_id, d.generator, d.method, d.confidence"
    )))
    assert rows == [["run-7", "rules.build_rules", "deterministic", 1.0]]


def test_a_rule_governs_the_field_its_component_edits(store) -> None:
    entity = SemanticEntity(
        name="checkout", description="d",
        fields=(SemanticField(
            name="email", data_type="email", required=True, validation="required",
            observed_values=(), derived_from=((PAGE, "input#a"),),
        ),),
        derived_from=((PAGE, "input#a"),),
    )
    store.record_entities([entity], run_id="run-1")
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    rows = store._call(lambda conn: list(conn.execute(
        "MATCH (:Rule {statement: 'required'})-[:GOVERNS]->(f:Field) RETURN f.name"
    )))
    assert rows == [["email"]]


def test_a_rule_writes_no_governs_edge_when_no_field_edits_its_component(store) -> None:
    """Best-effort GOVERNS: record_entities never ran, so no Field exists
    to attach to - the Rule and its DERIVED_FROM provenance still write."""
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    rows = store._call(lambda conn: list(conn.execute("MATCH ()-[g:GOVERNS]->() RETURN g")))
    assert rows == []
    assert [r.statement for r in store.get_rules()] == ["required"]


def test_recording_rules_does_not_wipe_entity_provenance(store) -> None:
    entity = SemanticEntity(
        name="checkout", description="d",
        fields=(SemanticField(
            name="email", data_type="email", required=True, validation="required",
            observed_values=(), derived_from=((PAGE, "input#a"),),
        ),),
        derived_from=((PAGE, "input#a"),),
    )
    store.record_entities([entity], run_id="run-1")

    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    assert [e.name for e in store.get_entities()] == ["checkout"]


def test_recording_entities_does_not_wipe_rule_provenance(store) -> None:
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    store.record_entities(build_entities([]), run_id="run-1")

    assert [r.statement for r in store.get_rules()] == ["required"]


# --- get_rule_field_entities ---


def test_a_governed_rule_reports_its_field_and_entity(store) -> None:
    entity = SemanticEntity(
        name="checkout", description="d",
        fields=(SemanticField(
            name="email", data_type="email", required=True, validation="required",
            observed_values=(), derived_from=((PAGE, "input#a"),),
        ),),
        derived_from=((PAGE, "input#a"),),
    )
    store.record_entities([entity], run_id="run-1")
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    rows = store.get_rule_field_entities()

    assert rows == [{
        "page_url": PAGE, "path": "input#a", "statement": "required",
        "field": "email", "entity": "checkout",
    }]


def test_an_ungoverned_rule_reports_no_field_entity_row(store) -> None:
    store.record_rules(build_rules([_input("input#a", required=True)]), run_id="run-1")

    assert store.get_rule_field_entities() == []
