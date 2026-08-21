"""Unit tests for generators/glossary.py - term extraction from
data-model.json's own recurring field names (docs/adr/0020)."""
from core.documents import DocumentRequest
from generators.glossary import GlossaryDocument, build_glossary_document, term_id
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/glossary.schema.json"


def _component(page, path, name, form, required=False):
    return {
        "page_url": page, "path": path, "component_type": "text field (text)",
        "name": name, "required": required, "input_type": "text",
        "tag": "input", "text": "", "label": "", "form": form,
    }


class _Store:
    def __init__(self, ledger):
        self._ledger = ledger

    def get_component_ledger(self):
        return self._ledger

    def get_inferred_requests(self):
        return []


def _request(ledger):
    return DocumentRequest(graph_store=_Store(ledger), site="shop.example", agent=None, settings={"run_id": "RUN-1"})


def _recurring_ledger():
    return {
        "shop.example/customer": {"input#email": _component("shop.example/customer", "input#email", "email", "form#customer")},
        "shop.example/order": {"input#email2": _component("shop.example/order", "input#email2", "email", "form#order")},
    }


# --- term_id ---

def test_term_id_is_deterministic_across_two_calls():
    assert term_id("email") == term_id("email")
    assert term_id("email").startswith("TERM-")


def test_term_id_is_case_insensitive():
    """The same term observed as "Email" and "email" mints one concept,
    not two."""
    assert term_id("Email") == term_id("email")


def test_term_id_differs_for_a_different_label():
    assert term_id("email") != term_id("quantity")


# --- build_glossary_document ---

def test_a_field_recurring_across_two_entities_becomes_a_term():
    document = build_glossary_document(_request(_recurring_ledger()))

    assert len(document["@graph"]) == 1
    concept = document["@graph"][0]
    assert concept["prefLabel"] == "email"
    assert concept["@id"] == term_id("email")


def test_a_field_declared_on_only_one_entity_is_not_promoted():
    ledger = {
        "shop.example/order": {
            "input#qty": _component("shop.example/order", "input#qty", "quantity", "form#order"),
        },
    }

    document = build_glossary_document(_request(ledger))

    assert document["@graph"] == []


def test_cross_references_cite_every_entity_the_term_was_observed_on():
    document = build_glossary_document(_request(_recurring_ledger()))

    assert document["@graph"][0]["cross_references"] == ["customer.email", "order.email"]


def test_broader_narrower_related_are_reserved_not_invented():
    document = build_glossary_document(_request(_recurring_ledger()))
    concept = document["@graph"][0]

    assert concept["broader"] == [] and concept["narrower"] == [] and concept["related"] == []


def test_derived_from_and_axtree_ref_are_reserved():
    document = build_glossary_document(_request(_recurring_ledger()))
    concept = document["@graph"][0]

    assert concept["derived_from"] == []
    assert concept["axtree_ref"] is None


def test_the_context_is_the_real_skos_namespace():
    document = build_glossary_document(_request(_recurring_ledger()))

    assert document["@context"] == "http://www.w3.org/2004/02/skos/core#"


def test_an_empty_crawl_produces_an_empty_graph_not_an_error():
    document = build_glossary_document(_request({}))

    assert document["@graph"] == []


# --- the document ---

def test_generate_returns_a_source_and_a_view_output():
    outputs = GlossaryDocument().outputs(_request(_recurring_ledger()))

    assert [(o.kind, o.extension) for o in outputs] == [("source", "jsonld"), ("view", "md")]


def test_the_view_lists_the_term_and_its_cross_references():
    view = GlossaryDocument().outputs(_request(_recurring_ledger()))[1].content

    assert "email" in view and "customer.email" in view and "order.email" in view


def test_no_recurring_term_is_stated_narrowly_not_as_a_bare_empty_note():
    view = GlossaryDocument().outputs(_request({}))[1].content

    assert "Read that narrowly" in view


def test_the_document_validates_against_its_own_schema():
    """No exception is the real assertion - generate() already calls
    validate_against_schema internally."""
    document = build_glossary_document(_request(_recurring_ledger()))

    validate_against_schema(document, _SCHEMA_PATH)
