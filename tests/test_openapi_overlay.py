"""Unit tests for generators/openapi_overlay.py's minimal JSONPath-subset
applier - pure logic, no graph store needed."""
import pytest

from generators.openapi_overlay import apply_overlay


def test_remove_deletes_the_matched_key():
    document = {"info": {"title": "x", "internal_note": "drop me"}}
    overlay = {"actions": [{"target": "$.info.internal_note", "remove": True}]}

    result = apply_overlay(document, overlay)

    assert "internal_note" not in result["info"]


def test_update_replaces_the_matched_value():
    document = {"info": {"contact": {"email": "real@example.com"}}}
    overlay = {"actions": [{"target": "$.info.contact.email", "update": "REDACTED"}]}

    result = apply_overlay(document, overlay)

    assert result["info"]["contact"]["email"] == "REDACTED"


def test_bracket_quoted_keys_reach_a_path_template_with_slashes_and_braces():
    document = {"paths": {"/orders/{orderId}": {"get": {"summary": "Get order"}}}}
    overlay = {"actions": [{"target": "$.paths['/orders/{orderId}'].get.summary", "update": "-"}]}

    result = apply_overlay(document, overlay)

    assert result["paths"]["/orders/{orderId}"]["get"]["summary"] == "-"


def test_wildcard_fans_out_over_every_operation_in_every_path():
    document = {
        "paths": {
            "/a": {"get": {"example": "secret-a"}},
            "/b": {"post": {"example": "secret-b"}},
        }
    }
    overlay = {"actions": [{"target": "$.paths[*][*].example", "remove": True}]}

    result = apply_overlay(document, overlay)

    assert "example" not in result["paths"]["/a"]["get"]
    assert "example" not in result["paths"]["/b"]["post"]


def test_a_target_that_matches_nothing_leaves_the_document_unchanged():
    document = {"info": {"title": "x"}}
    overlay = {"actions": [{"target": "$.info.does_not_exist", "remove": True}]}

    result = apply_overlay(document, overlay)

    assert result == document


def test_no_actions_is_a_no_op():
    document = {"info": {"title": "x"}}

    assert apply_overlay(document, {"actions": []}) == document
    assert apply_overlay(document, {}) == document


def test_the_original_document_is_never_mutated():
    document = {"info": {"secret": "keep-me-in-the-raw-file"}}
    overlay = {"actions": [{"target": "$.info.secret", "remove": True}]}

    apply_overlay(document, overlay)

    assert document["info"]["secret"] == "keep-me-in-the-raw-file"


def test_an_unrecognized_target_syntax_raises_rather_than_silently_matching_nothing():
    document = {"info": {"title": "x"}}
    overlay = {"actions": [{"target": "$.info[?(@.title)]", "remove": True}]}

    with pytest.raises(ValueError):
        apply_overlay(document, overlay)
