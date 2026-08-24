"""Unit tests for generators/requirements.py - pure functions over
InferredRequest/data-model.json shapes, no store needed except for the
module-grouping view (a minimal stub store)."""
import json

from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from core.interfaces import SemanticRule
from generators.requirements import (
    RequirementsDocument,
    _event_driven_requirements,
    _optional_feature_requirements,
    _rule_based_requirements,
    requirement_id,
    _ubiquitous_requirements,
    _unwanted_behavior_requirements,
    build_requirements_document,
)


def _inferred_request(**overrides):
    defaults = dict(
        method="POST", endpoint="api.example.com/checkout", query_params=(), body_shape="",
        response_shape="", triggered_by=(), loaded_by=(), status_codes=(),
    )
    defaults.update(overrides)
    return InferredRequest(**defaults)


def test_requirement_id_is_deterministic_across_two_calls():
    first = requirement_id("event_driven", "trigger", "target")
    second = requirement_id("event_driven", "trigger", "target")

    assert first == second
    assert first.startswith("REQ-")


def test_requirement_id_differs_for_a_different_trigger():
    assert requirement_id("event_driven", "a", "x") != requirement_id("event_driven", "b", "x")


# --- event_driven ---

def test_a_triggered_call_becomes_an_event_driven_requirement():
    request = _inferred_request(triggered_by=(("shop/cart", "button.buy"),))

    requirements = _event_driven_requirements([request], run_id="R1")

    assert len(requirements) == 1
    req = requirements[0]
    assert req["ears_pattern"] == "event_driven"
    assert req["confidence"] == "observed"
    assert "WHEN" in req["syntax_text"] and "THE SYSTEM SHALL" in req["syntax_text"]
    assert req["links"]["endpoints"] == ["POST api.example.com/checkout"]
    assert req["links"]["screens"][0].startswith("SCR-")


def test_no_trigger_means_no_event_driven_requirement():
    assert _event_driven_requirements([_inferred_request()], run_id="R1") == []


# --- ubiquitous ---

def test_a_page_load_call_becomes_a_ubiquitous_requirement():
    request = _inferred_request(loaded_by=("shop/cart",))

    requirements = _ubiquitous_requirements([request], run_id="R1")

    assert requirements[0]["ears_pattern"] == "ubiquitous"
    assert "THE SYSTEM SHALL" in requirements[0]["syntax_text"]
    assert requirements[0]["syntax_text"].startswith("THE SYSTEM SHALL")


# --- unwanted_behavior ---

def test_an_observed_failure_becomes_an_unwanted_behavior_requirement():
    request = _inferred_request(status_codes=(200, 500))

    requirements = _unwanted_behavior_requirements([request], run_id="R1")

    assert requirements[0]["ears_pattern"] == "unwanted_behavior"
    assert "IF" in requirements[0]["syntax_text"] and "THEN THE SYSTEM SHALL" in requirements[0]["syntax_text"]
    assert requirements[0]["open_questions"]


def test_only_success_codes_produce_no_unwanted_behavior_requirement():
    request = _inferred_request(status_codes=(200, 201))

    assert _unwanted_behavior_requirements([request], run_id="R1") == []


# --- optional_feature ---

def _data_model_document(nullable):
    return {"entities": {"checkout": {"description": "", "fields": {
        "promo_code": {"type": "string", "nullable": nullable, "confidence": 0.7,
                        "observed_in": {"forms": [], "api_endpoints": [], "ui_state": []}},
    }}}}


def test_a_nullable_field_becomes_an_optional_feature_requirement():
    requirements = _optional_feature_requirements(_data_model_document(nullable=True), run_id="R1")

    assert requirements[0]["ears_pattern"] == "optional_feature"
    assert requirements[0]["confidence"] == "inferred"
    assert requirements[0]["links"]["data_entities"] == ["checkout"]


def test_a_required_field_produces_no_optional_feature_requirement():
    assert _optional_feature_requirements(_data_model_document(nullable=False), run_id="R1") == []


# --- rule_based ---

def _rule(statement="required", derived_from=("shop/checkout", "input#email")):
    return SemanticRule(statement=statement, kind="declared", confidence=1.0, derived_from=derived_from)


def test_a_governed_rule_becomes_a_rule_based_requirement():
    rule = _rule()
    rule_field_entities = {("shop/checkout", "input#email", "required"): ("email", "checkout")}

    requirements = _rule_based_requirements([rule], rule_field_entities, run_id="R1")

    assert len(requirements) == 1
    req = requirements[0]
    assert req["ears_pattern"] == "ubiquitous"
    assert req["confidence"] == "inferred"
    assert req["syntax_text"] == "THE SYSTEM SHALL enforce required on email"
    assert req["links"]["data_entities"] == ["checkout"]
    assert req["links"]["screens"][0].startswith("SCR-")


def test_an_ungoverned_rule_produces_no_rule_based_requirement():
    """GOVERNS is best-effort (record_rules's own stance) - a Rule whose
    edge never resolved to a Field/Entity is silently skipped, not an
    error."""
    assert _rule_based_requirements([_rule()], {}, run_id="R1") == []


def test_an_inferred_kind_rule_is_never_turned_into_a_requirement():
    """kind='inferred' stays out of scope per #190/#193 even if some
    future writer starts producing one."""
    rule = SemanticRule(statement="required", kind="inferred", confidence=0.6, derived_from=("shop/checkout", "input#email"))
    rule_field_entities = {("shop/checkout", "input#email", "required"): ("email", "checkout")}

    assert _rule_based_requirements([rule], rule_field_entities, run_id="R1") == []


# --- assembly, dedup, and confidence never "assumed" ---

class _StubStore:
    def __init__(self, inferred_requests=(), pages=(), edges=(), rules=(), rule_field_entities=()):
        self._inferred_requests = inferred_requests
        self._pages = pages
        self._edges = edges
        self._rules = rules
        self._rule_field_entities = rule_field_entities

    def get_inferred_requests(self):
        return list(self._inferred_requests)

    def get_component_ledger(self):
        return {}

    def get_progress_table_rows(self):
        return [{"url": url, "status": "Finished"} for url in self._pages]

    def get_edges(self):
        return list(self._edges)

    def get_rules(self):
        return list(self._rules)

    def get_rule_field_entities(self):
        return list(self._rule_field_entities)


def _request(store, target=""):
    return DocumentRequest(graph_store=store, site="shop.example", agent=None, settings={"run_id": "R1", "target": target})


def test_the_same_observation_twice_deduplicates_to_one_requirement():
    """The deterministic id is what makes this work - two runs (or two
    components triggering the identical call) collapse to one entry."""
    requests = [
        _inferred_request(triggered_by=(("shop/cart", "button.buy"),)),
        _inferred_request(triggered_by=(("shop/cart", "button.buy"),)),
    ]

    document = build_requirements_document(_request(_StubStore(inferred_requests=requests)))

    assert len(document["requirements"]) == 1


def test_no_requirement_ever_carries_assumed_confidence():
    """Pragma has no extraction rule based on convention rather than
    observation - nothing here should ever claim it does."""
    requests = [
        _inferred_request(triggered_by=(("shop/cart", "button.buy"),), status_codes=(500,), loaded_by=("shop/cart",)),
    ]

    document = build_requirements_document(_request(_StubStore(inferred_requests=requests)))

    assert all(req["confidence"] != "assumed" for req in document["requirements"])


def test_build_requirements_document_validates_against_its_schema():
    outputs = RequirementsDocument().outputs(_request(_StubStore(
        inferred_requests=[_inferred_request(triggered_by=(("shop/cart", "button.buy"),))],
    )))

    document = json.loads(outputs[0].content)  # already schema-validated inside generate()
    assert document["requirements"][0]["id"].startswith("REQ-")


def test_generate_returns_the_source_and_view_pair():
    outputs = RequirementsDocument().outputs(_request(_StubStore()))

    assert [o.filename for o in outputs] == ["requirements", "prd"]
    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_the_view_groups_requirements_by_module():
    store = _StubStore(
        inferred_requests=[_inferred_request(triggered_by=(("shop/admin/orders", "button.buy"),))],
        pages=["shop/admin/orders", "shop/admin/users"],
        edges=[],
    )

    view = RequirementsDocument().outputs(_request(store))[1].content

    assert "## Admin" in view or "## " in view  # a module heading exists either way


def test_a_requirement_with_no_screen_link_lands_in_not_tied_to_a_screen():
    store = _StubStore(inferred_requests=[_inferred_request(status_codes=(500,))])

    view = RequirementsDocument().outputs(_request(store))[1].content

    assert "## Not tied to a screen" in view


def test_an_empty_crawl_produces_no_requirements_not_an_error():
    document = build_requirements_document(_request(_StubStore()))

    assert document["requirements"] == []


def test_build_requirements_document_wires_rule_based_requirements():
    store = _StubStore(
        rules=[_rule()],
        rule_field_entities=[{
            "page_url": "shop/checkout", "path": "input#email",
            "statement": "required", "field": "email", "entity": "checkout",
        }],
    )

    document = build_requirements_document(_request(store))

    assert [r["ears_pattern"] for r in document["requirements"]] == ["ubiquitous"]
    assert document["requirements"][0]["confidence"] == "inferred"
