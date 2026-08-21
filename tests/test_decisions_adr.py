"""Unit tests for generators/decisions_adr.py - one MADR file per
inferred/assumed requirement (docs/adr/0023)."""
from core.documents import DocumentRequest
from generators.decisions_adr import DecisionsAdrDocument, _slug, decision_entities


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


def _one_nullable_field_ledger():
    """A `newsletter` field, not required (nullable) - the one path that
    reaches `_optional_feature_requirements`'s `"inferred"` confidence."""
    return {
        "shop.example/customer": {
            "input#newsletter": _component("shop.example/customer", "input#newsletter", "newsletter", "form#customer", required=False),
        },
    }


def _no_nullable_field_ledger():
    return {
        "shop.example/customer": {
            "input#email": _component("shop.example/customer", "input#email", "email", "form#customer", required=True),
        },
    }


# --- _slug ---

def test_slug_lowercases_and_hyphenates():
    assert _slug("WHERE the user provides X") == "where-the-user-provides-x"


def test_slug_is_truncated_not_left_unbounded():
    assert len(_slug("a" * 200)) <= 60


# --- decision_entities ---

def test_a_nullable_field_produces_one_inferred_decision():
    entities = decision_entities(_request(_one_nullable_field_ledger()))

    assert len(entities) == 1
    assert entities[0]["confidence"] == "inferred"
    assert entities[0]["ears_pattern"] == "optional_feature"


def test_a_required_field_produces_no_decision():
    """`required=True` means not nullable - nothing here for
    decisions.adr/ to explain."""
    entities = decision_entities(_request(_no_nullable_field_ledger()))

    assert entities == []


def test_no_form_data_at_all_produces_no_decision_not_an_error():
    entities = decision_entities(_request({}))

    assert entities == []


# --- the document ---

def test_generate_writes_one_numbered_madr_file_per_decision():
    outputs = DecisionsAdrDocument().outputs(_request(_one_nullable_field_ledger()))

    assert len(outputs) == 1
    output = outputs[0]
    assert output.filename.startswith("decisions.adr/0001-")
    assert output.kind == "projection"
    assert output.extension == "md"


def test_zero_decisions_means_zero_files_not_an_empty_placeholder():
    outputs = DecisionsAdrDocument().outputs(_request(_no_nullable_field_ledger()))

    assert outputs == ()


def test_the_file_cites_the_requirement_id_as_a_cross_reference():
    outputs = DecisionsAdrDocument().outputs(_request(_one_nullable_field_ledger()))
    entities = decision_entities(_request(_one_nullable_field_ledger()))

    assert entities[0]["id"] in outputs[0].content


def test_the_file_states_the_confidence_and_never_claims_observed():
    outputs = DecisionsAdrDocument().outputs(_request(_one_nullable_field_ledger()))

    content = outputs[0].content
    assert "`inferred`" in content
    assert "Classified `inferred`, not `observed`" in content


def test_numbering_is_sequential_across_several_decisions():
    ledger = {
        "shop.example/customer": {
            "input#a": _component("shop.example/customer", "input#a", "a", "form#customer", required=False),
        },
        "shop.example/order": {
            "input#b": _component("shop.example/order", "input#b", "b", "form#order", required=False),
        },
    }

    outputs = DecisionsAdrDocument().outputs(_request(ledger))

    filenames = sorted(output.filename for output in outputs)
    assert filenames[0].startswith("decisions.adr/0001-")
    assert filenames[1].startswith("decisions.adr/0002-")
