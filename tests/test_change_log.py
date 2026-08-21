"""Unit tests for generators/change_log.py - the diff_entities algorithm
(docs/adr/0019), proven against synthetic two-run fixtures per the
ticket's own "Done when" criterion. Real store-backed snapshot extraction
(_snapshots_from_export_graph) is exercised end-to-end in
test_document_pipeline.py-style fixtures, not duplicated here."""
import json

from core.documents import DocumentRequest
from generators.change_log import (
    ChangeLogDocument,
    diff_entities,
)
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/change-log.schema.json"


class _EmptyStore:
    """Enough of a store surface for build_export_graph to run against an
    empty crawl - every real read returns nothing."""

    def get_progress_table_rows(self):
        return []

    def get_page_titles(self):
        return {}

    def get_page_descriptions(self):
        return {}

    def get_component_ledger(self):
        return {}

    def get_inferred_requests(self):
        return []

    def get_edges(self):
        return []

    def get_page_landmarks(self):
        return {}

    def get_text_content_ledger(self):
        return {}

    def get_state_styles(self):
        return {}

    def get_component_families(self):
        return []


def _request(settings=None):
    return DocumentRequest(graph_store=_EmptyStore(), site="shop.example", agent=None, settings=settings or {})


# --- diff_entities: the three-way split (ADR-0019 point 2) ---

def test_an_id_only_in_current_is_newly_discovered():
    diff = diff_entities({}, {"REQ-a": {"syntax_text": "x"}})

    assert diff.newly_discovered == ("REQ-a",)
    assert diff.no_longer_observed == () and diff.changed == ()


def test_an_id_only_in_previous_is_no_longer_observed():
    diff = diff_entities({"REQ-a": {"syntax_text": "x"}}, {})

    assert diff.no_longer_observed == ("REQ-a",)
    assert diff.newly_discovered == () and diff.changed == ()


def test_the_same_id_with_an_unchanged_field_produces_no_entry():
    entity = {"syntax_text": "x", "confidence": "observed"}

    diff = diff_entities({"REQ-a": entity}, {"REQ-a": dict(entity)})

    assert diff.newly_discovered == () and diff.no_longer_observed == () and diff.changed == ()


def test_the_same_id_with_a_changed_field_is_changed_not_newly_discovered():
    diff = diff_entities(
        {"REQ-a": {"confidence": "observed"}},
        {"REQ-a": {"confidence": "inferred"}},
    )

    assert diff.newly_discovered == () and diff.no_longer_observed == ()
    assert len(diff.changed) == 1
    assert diff.changed[0].id == "REQ-a"
    assert diff.changed[0].changed_fields == ("confidence",)


def test_a_field_added_or_removed_counts_as_changed_too():
    diff = diff_entities({"REQ-a": {"x": 1}}, {"REQ-a": {"x": 1, "y": 2}})

    assert diff.changed[0].changed_fields == ("y",)


def test_an_identity_field_change_is_a_discovered_plus_no_longer_observed_pair():
    """The nuance ADR-0019 point 2 documents: an identity-defining field
    change mints a *different* Short hash id, so it can never appear as
    a `changed` entry - only as this exact pair, because the two ids are
    different dict keys by construction, not because this function
    special-cases identity fields."""
    old_id = "REQ-abc1234567"  # would have hashed from the OLD trigger/target
    new_id = "REQ-def7654321"  # hashes from the NEW trigger/target

    diff = diff_entities(
        {old_id: {"syntax_text": "WHEN the user interacts with a, THE SYSTEM SHALL call X"}},
        {new_id: {"syntax_text": "WHEN the user interacts with b, THE SYSTEM SHALL call X"}},
    )

    assert diff.newly_discovered == (new_id,)
    assert diff.no_longer_observed == (old_id,)
    assert diff.changed == ()


def test_results_are_sorted_for_a_deterministic_document():
    diff = diff_entities({}, {"REQ-b": {}, "REQ-a": {}})

    assert diff.newly_discovered == ("REQ-a", "REQ-b")


# --- build_change_log_document / the document ---

def test_with_no_previous_snapshot_the_diff_is_honestly_empty():
    """Absence of a previous snapshot must not read as "everything is
    newly discovered" - that would misrepresent a single-run site."""
    outputs = ChangeLogDocument().outputs(_request({"run_id": "RUN-1"}))
    document = json.loads(outputs[0].content)

    assert document["run_id_from"] is None
    assert document["run_id_to"] == "RUN-1"
    for kind_diff in document["kinds"].values():
        assert kind_diff == {"newly_discovered": [], "no_longer_observed": [], "changed": []}


def test_with_no_previous_snapshot_the_view_says_so():
    view = ChangeLogDocument().outputs(_request())[1].content

    assert "nothing to diff yet" in view


def test_with_a_previous_snapshot_a_real_diff_is_computed():
    previous_snapshot = {
        "screens": {}, "requirements": {"REQ-old0000000": {"syntax_text": "old"}},
        "endpoints": {}, "modules": {}, "channels": {}, "messages": {},
    }
    outputs = ChangeLogDocument().outputs(
        _request({"run_id": "RUN-2", "previous_run_id": "RUN-1", "previous_snapshot": previous_snapshot})
    )
    document = json.loads(outputs[0].content)

    assert document["run_id_from"] == "RUN-1"
    assert document["kinds"]["requirements"]["no_longer_observed"] == ["REQ-old0000000"]


def test_channels_and_messages_are_always_empty_kinds():
    """No real detection instrumentation exists for either yet
    (ADR-0018) - present in the shape, never populated."""
    document = json.loads(ChangeLogDocument().outputs(_request())[0].content)

    assert document["kinds"]["channels"] == {"newly_discovered": [], "no_longer_observed": [], "changed": []}
    assert document["kinds"]["messages"] == {"newly_discovered": [], "no_longer_observed": [], "changed": []}


def test_generate_returns_a_source_and_a_view_output():
    outputs = ChangeLogDocument().outputs(_request())

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_the_document_validates_against_its_own_schema():
    """No exception is the real assertion - generate() already calls
    validate_against_schema internally."""
    outputs = ChangeLogDocument().outputs(_request())

    validate_against_schema(json.loads(outputs[0].content), _SCHEMA_PATH)
