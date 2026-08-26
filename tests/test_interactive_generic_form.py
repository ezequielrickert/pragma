"""Unit tests for interactive/generic_form.py - ADR-0034's field-level
HITL allowlist and its schema-driven widget resolution (ticket #158)."""
import json
from typing import Any

from interactive.customization import DocumentRef, SiteOutput, effective_content
from interactive.generic_form import (
    Widget,
    _entries,
    _entry_schema,
    _is_nullable,
    _widget_for,
    form_entries,
    has_generic_form,
    save_generic_form,
)

SITE = "example.com"


def _saved(where: SiteOutput, ref: DocumentRef) -> Any:
    """`effective_content` returns `None` for a document never produced -
    every caller here already wrote one, so a `None` here would itself
    be the test failure worth seeing, not a value to silently swallow."""
    content = effective_content(where, ref)
    assert content is not None
    return json.loads(content)


def _where(tmp_path) -> SiteOutput:
    return SiteOutput(out_dir=str(tmp_path), site=SITE)


def _write_requirements(tmp_path, requirements):
    payload = {"requirements": requirements}
    (tmp_path / f"{SITE}_requirements_20260101T000000Z.json").write_text(json.dumps(payload), encoding="utf-8")


def _requirement(**overrides):
    base = {
        "id": "REQ-a4f9000001", "ears_pattern": "event_driven", "syntax_text": "WHEN x, THE SYSTEM SHALL y",
        "confidence": "observed", "derived_from": [], "coverage_ref": {"run_id": "RUN-1"},
        "links": {"screens": [], "endpoints": [], "scenarios": [], "data_entities": [], "depends_on": []},
        "hitl_status": "unreviewed", "open_questions": [],
    }
    base.update(overrides)
    return base


# --- widget resolution (schema construct -> widget), no document involved ---

def test_widget_for_enum_is_select():
    assert _widget_for({"enum": ["a", "b"]}) is Widget.SELECT


def test_widget_for_array_of_strings_is_textarea():
    assert _widget_for({"type": "array", "items": {"type": "string"}}) is Widget.TEXTAREA


def test_widget_for_nullable_string_is_text():
    assert _widget_for({"type": ["string", "null"]}) is Widget.TEXT


def test_widget_for_plain_string_is_text():
    assert _widget_for({"type": "string"}) is Widget.TEXT


def test_is_nullable_true_for_string_or_null():
    assert _is_nullable({"type": ["string", "null"]}) is True


def test_is_nullable_false_for_a_plain_string():
    assert _is_nullable({"type": "string"}) is False


# --- schema/document resolution, both array_path shapes ---

def test_entry_schema_resolves_a_ref_when_array_path_is_set():
    """requirements.schema.json's own shape - items is a $ref, not
    inline."""
    schema = {
        "properties": {"requirements": {"type": "array", "items": {"$ref": "#/$defs/requirement"}}},
        "$defs": {"requirement": {"type": "object", "properties": {"hitl_status": {"enum": ["a"]}}}},
    }
    from interactive.generic_form import GenericFormSpec

    spec = GenericFormSpec(array_path="requirements", hitl_fields=["hitl_status"], summary_fields=[])

    resolved = _entry_schema(schema, spec)

    assert resolved == {"type": "object", "properties": {"hitl_status": {"enum": ["a"]}}}


def test_entry_schema_resolves_inline_items_when_array_path_is_none():
    """The other real shape (browser-support-matrix.schema.json's own,
    even though it's not a live GENERIC_FORM_SPECS entry today) - the
    document's own root is the array, items named inline, no $ref."""
    from interactive.generic_form import GenericFormSpec

    schema = {"type": "array", "items": {"type": "object", "properties": {"business_reason": {"type": ["string", "null"]}}}}
    spec = GenericFormSpec(array_path=None, hitl_fields=["business_reason"], summary_fields=[])

    resolved = _entry_schema(schema, spec)

    assert resolved == {"type": "object", "properties": {"business_reason": {"type": ["string", "null"]}}}


def test_entries_with_array_path_set_reads_the_nested_property():
    from interactive.generic_form import GenericFormSpec

    spec = GenericFormSpec(array_path="requirements", hitl_fields=[], summary_fields=[])

    assert _entries({"requirements": [{"id": 1}]}, spec) == [{"id": 1}]


def test_entries_with_array_path_none_reads_the_document_root():
    from interactive.generic_form import GenericFormSpec

    spec = GenericFormSpec(array_path=None, hitl_fields=[], summary_fields=[])

    assert _entries([{"kind": "polyfill"}], spec) == [{"kind": "polyfill"}]


# --- has_generic_form ---

def test_has_generic_form_is_true_for_requirements():
    assert has_generic_form("requirements") is True


def test_has_generic_form_is_false_for_a_document_with_no_spec():
    """browser-support-matrix has a real schema and a real HITL-shaped
    field, but its own generator never produces it (see this module's
    docstring) - deliberately absent from GENERIC_FORM_SPECS."""
    assert has_generic_form("browser-support-matrix") is False
    assert has_generic_form("gherkin") is False


# --- form_entries (read path) ---

def test_form_entries_reads_every_requirement_with_its_hitl_fields(tmp_path):
    _write_requirements(tmp_path, [
        _requirement(id="REQ-1111111111", syntax_text="first", hitl_status="unreviewed"),
        _requirement(id="REQ-2222222222", syntax_text="second", hitl_status="approved", open_questions=["q1"]),
    ])

    entries = form_entries(_where(tmp_path), DocumentRef("requirements", "json"))

    assert [entry.summary for entry in entries] == ["REQ-1111111111 - first", "REQ-2222222222 - second"]
    first_status = next(f for f in entries[0].fields if f.name == "hitl_status")
    assert first_status.widget is Widget.SELECT
    assert first_status.value == "unreviewed"
    assert first_status.options == ["unreviewed", "approved", "rejected"]
    second_questions = next(f for f in entries[1].fields if f.name == "open_questions")
    assert second_questions.widget is Widget.TEXTAREA
    assert second_questions.value == "q1"


def test_form_entries_is_empty_for_a_document_with_no_spec(tmp_path):
    (tmp_path / f"{SITE}_gherkin_20260101T000000Z.feature").write_text("Feature: x\n", encoding="utf-8")

    assert form_entries(_where(tmp_path), DocumentRef("gherkin", "feature")) == []


def test_form_entries_is_empty_when_the_document_was_never_produced(tmp_path):
    assert form_entries(_where(tmp_path), DocumentRef("requirements", "json")) == []


# --- save_generic_form (write path) ---

def test_save_generic_form_patches_only_the_targeted_row_and_field(tmp_path):
    _write_requirements(tmp_path, [
        _requirement(id="REQ-1111111111", hitl_status="unreviewed"),
        _requirement(id="REQ-2222222222", hitl_status="unreviewed"),
    ])
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {1: {"hitl_status": "approved"}})

    saved = _saved(where, ref)
    assert saved["requirements"][0]["hitl_status"] == "unreviewed"
    assert saved["requirements"][1]["hitl_status"] == "approved"


def test_save_generic_form_splits_textarea_lines_and_drops_blanks(tmp_path):
    _write_requirements(tmp_path, [_requirement()])
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {0: {"open_questions": "first question?\n\nsecond question?\n"}})

    saved = _saved(where, ref)
    assert saved["requirements"][0]["open_questions"] == ["first question?", "second question?"]


def test_save_generic_form_ignores_a_stale_row_index(tmp_path):
    _write_requirements(tmp_path, [_requirement(hitl_status="unreviewed")])
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {5: {"hitl_status": "approved"}})

    saved = _saved(where, ref)
    assert saved["requirements"][0]["hitl_status"] == "unreviewed"


def test_save_generic_form_ignores_a_field_not_on_the_allowlist(tmp_path):
    """A submission can't smuggle an edit to a generated field
    (`syntax_text`) just by crafting the right form key - only
    `spec.hitl_fields` are ever written."""
    _write_requirements(tmp_path, [_requirement(syntax_text="original")])
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {0: {"syntax_text": "tampered"}})

    saved = _saved(where, ref)
    assert saved["requirements"][0]["syntax_text"] == "original"


def test_save_generic_form_writes_a_schema_valid_document(tmp_path):
    """The write path is the real save_customized - a broken document
    would raise here exactly like it does for the raw-text editor."""
    _write_requirements(tmp_path, [_requirement()])
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {0: {"hitl_status": "approved"}})

    saved = _saved(where, ref)
    assert saved["requirements"][0]["hitl_status"] == "approved"
    assert saved["requirements"][0]["id"] == "REQ-a4f9000001"  # untouched fields survive


def test_save_generic_form_is_a_no_op_when_the_document_was_never_produced(tmp_path):
    """No original, no customized copy - nothing to patch, and no
    crash either."""
    where = _where(tmp_path)
    ref = DocumentRef("requirements", "json")

    save_generic_form(where, ref, {0: {"hitl_status": "approved"}})

    assert effective_content(where, ref) is None
