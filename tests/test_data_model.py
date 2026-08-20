"""Unit tests for the data model (generators/data_model.py) - pure functions
over hand-built ledger rows - plus the semantic tier's write path
(database/ladybug/semantic.py) against the real engine.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.interfaces import SemanticEntity, SemanticField
from database.ladybug.store import LadybugGraphStore
from generators.data_model import (
    DataModelDocument,
    _api_citations,
    _gaps,
    _mermaid_er_diagram,
    _privacy_annotation,
    build_data_model_document,
    build_entities,
)

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

class _StubStore:
    def __init__(self, ledger):
        self._ledger = ledger

    def get_component_ledger(self):
        return self._ledger

    def get_inferred_requests(self):
        return []


def _stub_request(ledger, coverage=None):
    from core.documents import DocumentRequest

    return DocumentRequest(
        graph_store=_StubStore(ledger), site="shop.example", agent=None,
        settings={"run_id": "R1"}, coverage=coverage,
    )


def test_the_document_lists_each_form_with_its_evidence():
    ledger = {PAGE: {"input#a": _input("input#a", input_type="email", required=True)}}

    outputs = DataModelDocument().outputs(_stub_request(ledger))
    view = outputs[1].content

    assert "## checkout" in view
    assert "string (email)" in view


def test_a_crawl_with_no_forms_says_which_two_causes_are_open():
    outputs = DataModelDocument().outputs(_stub_request({}))
    view = outputs[1].content

    assert "No forms with named inputs were found" in view
    assert "the two look the same here" in view


# --- privacy heuristic (docs/adr/0008 point 1) ---

def test_an_email_field_is_flagged_as_pii():
    privacy = _privacy_annotation("email")

    assert privacy == {"is_pii": True, "category": "dpv:PersonalData", "dpv_type": "dpv:EmailAddress", "sensitivity": "medium"}


def test_a_password_field_is_flagged_high_sensitivity():
    privacy = _privacy_annotation("password")

    assert privacy["sensitivity"] == "high"


def test_an_unrecognized_field_name_gets_no_privacy_object():
    """Absent, not a false is_pii: false - this heuristic has no opinion
    about a field named "quantity"."""
    assert _privacy_annotation("quantity") is None


def test_the_signal_match_is_a_substring_not_an_exact_name():
    assert _privacy_annotation("billing_address") is not None
    assert _privacy_annotation("user_email_confirm") is not None


# --- API-traffic correlation (docs/adr/0008 point 2) ---

def _inferred_request(method="POST", endpoint="api.example.com/checkout", body_shape="", response_shape=""):
    return SimpleNamespace(method=method, endpoint=endpoint, body_shape=body_shape, response_shape=response_shape)


def test_a_field_present_in_a_request_body_is_cited():
    """The format audit's own complaint: a field the API carries but no
    form exposes must not be undercounted."""
    requests = [_inferred_request(body_shape='{"email": "string"}')]

    citations = _api_citations("email", requests)

    assert citations == ("POST api.example.com/checkout",)


def test_a_field_present_only_in_a_response_body_is_also_cited():
    requests = [_inferred_request(method="GET", response_shape='{"email": "string"}')]

    assert _api_citations("email", requests) == ("GET api.example.com/checkout",)


def test_field_name_matching_is_case_insensitive():
    requests = [_inferred_request(body_shape='{"Email": "string"}')]

    assert _api_citations("email", requests) == ("POST api.example.com/checkout",)


def test_a_field_absent_from_every_shape_is_not_cited():
    requests = [_inferred_request(body_shape='{"quantity": "number"}')]

    assert _api_citations("email", requests) == ()


def test_an_unparseable_shape_is_skipped_not_a_crash():
    requests = [_inferred_request(body_shape="not json")]

    assert _api_citations("email", requests) == ()


# --- coverage gaps (docs/adr/0008 point 3) ---

def test_a_gap_is_recorded_per_unfinished_page():
    coverage = SimpleNamespace(unfinished_urls=["shop.example/checkout/payment"])

    gaps = _gaps(coverage, run_id="RUN-1")

    assert gaps == [{
        "entity": "shop.example/checkout/payment", "reason": "unvisited_route",
        "coverage_ref": {"run_id": "RUN-1", "unvisited_endpoint": "shop.example/checkout/payment"},
    }]


def test_no_coverage_means_no_gaps_not_a_crash():
    assert _gaps(None, run_id="RUN-1") == []


# --- Mermaid erDiagram (docs/adr/0008 point 4) ---

def test_the_mermaid_block_declares_one_entity_per_form():
    document = {"entities": {
        "checkout": {"description": "", "fields": {"email": {"type": "string", "format": "", "nullable": False, "confidence": 0.7, "observed_in": {"forms": [], "api_endpoints": [], "ui_state": []}}}},
    }}

    block = _mermaid_er_diagram(document)

    assert block.startswith("```mermaid\nerDiagram")
    assert "checkout {" in block
    assert "string email" in block
    assert block.endswith("```")


# --- full document assembly + schema validation ---

def test_build_data_model_document_validates_against_its_schema():
    ledger = {PAGE: {"input#a": _input("input#a", name="email", input_type="email")}}
    outputs = DataModelDocument().outputs(_stub_request(ledger))

    document = json.loads(outputs[0].content)  # generate() already schema-validated; confirm parseable
    assert "checkout" in document["entities"]
    assert document["entities"]["checkout"]["fields"]["email"]["privacy"]["dpv_type"] == "dpv:EmailAddress"


def test_build_data_model_document_carries_coverage_gaps():
    coverage = SimpleNamespace(unfinished_urls=["shop.example/other"])
    outputs = DataModelDocument().outputs(_stub_request({}, coverage=coverage))

    document = json.loads(outputs[0].content)
    assert document["gaps"][0]["entity"] == "shop.example/other"
