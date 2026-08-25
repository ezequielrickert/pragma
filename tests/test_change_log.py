"""Unit tests for generators/change_log.py - the diff_entities algorithm
(docs/adr/0019), proven against synthetic two-run fixtures per the
ticket's own "Done when" criterion. Real store-backed snapshot extraction
(_snapshots_from_export_graph) is exercised end-to-end in
test_document_pipeline.py-style fixtures, not duplicated here."""
from generators.change_log import diff_entities

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


