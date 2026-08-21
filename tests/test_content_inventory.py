"""Unit tests for generators/content_inventory.py - copy/microcopy/legal
text cited by component instance (docs/adr/0025)."""
from core.documents import DocumentRequest
from core.interfaces import ComponentFamily
from generators.content_inventory import (
    ContentInventoryDocument,
    _glossary_ref,
    _is_legal,
    build_content_inventory,
)
from utils.schema_validation import validate_against_schema

PAGE = "shop/"
_SCHEMA_PATH = "schemas/content-inventory.schema.json"


def _member(path, text, tag="button", form="", required=False, page=PAGE, **facts):
    row = {
        "page_url": page, "path": path, "tag": tag, "text": text,
        "css_class": "btn", "background_color": "", "label": "", "placeholder": "",
        "name": "", "href": "", "form": form, "required": required, "disabled": False,
        "options": ([], ""), "input_type": "text", "component_type": "button",
    }
    row.update(facts)
    return row


def _field(path, form, name, page=PAGE, required=False):
    """A data-model.py-shaped field member - `component_type` must start
    with a real field-type prefix (`_is_field`) for `group_form_components`
    to include it, unlike a catalog member's own default "button" type."""
    return _member(
        path, "", tag="input", form=form, required=required, page=page,
        name=name, component_type="text field (text)",
    )


def _family(paths, tag="button", component_type="button", common=("btn",)):
    """`paths` is a bare path string (assumed on `PAGE`) or a `(page, path)`
    pair, matching whatever `_member` calls actually used - `used_on` is
    derived from the ledger member's own real `page_url`, not this
    family's page assumption, so the two must agree."""
    member_paths = tuple(entry if isinstance(entry, tuple) else (PAGE, entry) for entry in paths)
    return ComponentFamily(
        tag=tag, component_type=component_type, common_classes=tuple(common),
        member_paths=member_paths, purpose="",
    )


class _Store:
    def __init__(self, families, members):
        self._families = families
        self._members = members

    def get_component_families(self):
        return self._families

    def get_component_ledger(self):
        return {PAGE: {member["path"]: member for member in self._members}}

    def get_component_regions(self):
        return {}

    def get_state_styles(self):
        return []

    def get_inferred_requests(self):
        return []


def _request(store):
    return DocumentRequest(graph_store=store, site="shop.example", agent=None)


# --- _is_legal ---

def test_a_privacy_policy_reference_is_flagged_legal():
    assert _is_legal("See our Privacy Policy for details.") is True


def test_ordinary_copy_is_not_flagged():
    assert _is_legal("Add to cart") is False


def test_the_match_is_case_insensitive():
    assert _is_legal("ALL RIGHTS RESERVED") is True


# --- _glossary_ref ---

def test_a_matching_term_returns_its_hash():
    labels = {"email": "TERM-abc123"}

    assert _glossary_ref("Email", labels) == "TERM-abc123"


def test_no_matching_term_returns_none_not_a_placeholder_string():
    assert _glossary_ref("Add to cart", {}) is None


# --- build_content_inventory ---

def test_a_variant_with_text_produces_one_entry_citing_its_component_and_variant():
    store = _Store([_family(["a"])], [_member("a", "Comprar")])

    entries = build_content_inventory(_request(store))

    assert len(entries) == 1
    assert entries[0]["component_ref"] == "Button#variant-1"
    assert entries[0]["text"] == "Comprar"
    assert entries[0]["is_legal"] is False
    assert entries[0]["requires_review"] is False
    assert entries[0]["glossary_ref"] is None


def test_a_variant_with_no_text_contributes_no_entry():
    store = _Store([_family(["a"])], [_member("a", "")])

    assert build_content_inventory(_request(store)) == []


def test_legal_copy_sets_both_is_legal_and_requires_review():
    store = _Store([_family(["a"])], [_member("a", "Read our Terms of Service")])

    entries = build_content_inventory(_request(store))

    assert entries[0]["is_legal"] is True
    assert entries[0]["requires_review"] is True


def test_screens_cite_every_page_the_component_is_used_on():
    store = _Store(
        [_family([("shop/cart", "a"), ("shop/checkout", "b")])],
        [_member("a", "Comprar", page="shop/cart"), _member("b", "Comprar", page="shop/checkout")],
    )

    entries = build_content_inventory(_request(store))

    assert len(entries[0]["screens"]) == 2
    assert all(screen.startswith("SCR-") for screen in entries[0]["screens"])


def test_a_recurring_nullable_field_name_matching_observed_text_completes_the_glossary_cross_reference():
    """glossary.jsonld promotes "newsletter" once it recurs across two
    forms - a catalog variant whose own text is that same string cites
    the resulting TERM-<hash> back."""
    members = [
        _member("btn", "Newsletter", tag="button"),
        _field("f1", "form#customer", "newsletter"),
        _field("f2", "form#order", "newsletter"),
    ]
    store = _Store([_family(["btn"])], members)

    entries = build_content_inventory(_request(store))

    button_entry = next(entry for entry in entries if entry["component_ref"] == "Button#variant-1")
    assert button_entry["glossary_ref"] is not None
    assert button_entry["glossary_ref"].startswith("TERM-")


# --- the document ---

def test_generate_returns_a_source_and_a_view_output():
    store = _Store([_family(["a"])], [_member("a", "Comprar")])

    outputs = ContentInventoryDocument().outputs(_request(store))

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_no_observed_text_produces_an_honest_empty_note():
    store = _Store([_family(["a"])], [_member("a", "")])

    view = ContentInventoryDocument().outputs(_request(store))[1].content

    assert "No component instance" in view


def test_the_document_validates_against_its_own_schema():
    store = _Store([_family(["a"])], [_member("a", "Read our Privacy Policy")])

    entries = build_content_inventory(_request(store))

    validate_against_schema(entries, _SCHEMA_PATH)
