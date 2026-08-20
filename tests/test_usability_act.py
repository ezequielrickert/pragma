"""Unit tests for generators/usability_act.py - the ACT/EARL/SARIF
serialization layer over usability.py's own findings."""
import json

from core.documents import DocumentRequest
from generators.usability import Finding, build_findings
from generators.usability_act import (
    _RULE_CATALOG,
    _RULE_ID_BY_FINDING_RULE,
    UsabilityDocument,
    build_earl_document,
    build_rule_catalog,
    build_sarif_document,
)


class _EmptyStore:
    def get_component_ledger(self):
        return {}

    def get_edges(self):
        return []

    def get_component_families(self):
        return []

    def get_inferred_requests(self):
        return []

    def get_text_content_ledger(self):
        return {}


def _request(settings=None):
    return DocumentRequest(graph_store=_EmptyStore(), site="shop.example", agent=None, settings=settings or {"run_id": "R1"})


# --- rule catalog ---

def test_every_finding_rule_usability_py_can_produce_has_a_catalog_entry():
    """A detection rule with no matching catalog entry would crash the
    EARL assembly the moment it fired - this test catches that before a
    real crawl does."""
    known_finding_rules = {
        "inconsistent-family-styling", "inconsistent-action-naming", "missing-semantic-input-type",
        "unexplained-disabled-control", "dead-end-screen",
    }

    assert set(_RULE_ID_BY_FINDING_RULE) == known_finding_rules
    assert set(_RULE_ID_BY_FINDING_RULE.values()) == {rule.id for rule in _RULE_CATALOG}


def test_the_rule_catalog_validates_and_carries_nielsen_heuristics():
    catalog = build_rule_catalog()

    assert len(catalog["rules"]) == len(_RULE_CATALOG)
    assert all(rule["x-nielsen-heuristic"] for rule in catalog["rules"])
    assert all(rule["id"].startswith("RULE-") for rule in catalog["rules"])


# --- EARL assembly ---

def _finding(rule="inconsistent-family-styling", severity="medium"):
    return Finding(
        rule=rule, heuristic="Consistency and standards", severity=severity,
        where="shop.example/checkout — button.buy", detail="Two shades of the same button.",
        recommendation="Pick one token.",
    )


def test_earl_document_has_one_assertion_per_finding(monkeypatch):
    monkeypatch.setattr("generators.usability_act.build_findings", lambda request: [_finding(), _finding("dead-end-screen")])

    document = build_earl_document(_request())

    assert document["@context"] == "https://www.w3.org/ns/earl"
    assert len(document["@graph"]) == 2


def test_earl_assertion_carries_the_rule_id_and_level(monkeypatch):
    monkeypatch.setattr("generators.usability_act.build_findings", lambda request: [_finding(severity="high")])

    assertion = build_earl_document(_request())["@graph"][0]

    assert assertion["test"]["@id"] == "RULE-consistency-and-standards-01"
    assert assertion["level"] == "error"
    assert assertion["mode"] == "earl:automatic"


def test_earl_assertion_reserved_fields_are_empty_not_invented(monkeypatch):
    monkeypatch.setattr("generators.usability_act.build_findings", lambda request: [_finding()])

    assertion = build_earl_document(_request())["@graph"][0]

    assert assertion["derived_from"] == []
    assert assertion["axtree_ref"] is None


def test_coverage_ref_carries_the_real_run_id(monkeypatch):
    monkeypatch.setattr("generators.usability_act.build_findings", lambda request: [_finding()])

    assertion = build_earl_document(_request(settings={"run_id": "RUN-42"}))["@graph"][0]

    assert assertion["coverage_ref"]["run_id"] == "RUN-42"


def test_no_findings_is_an_empty_graph_not_an_error():
    document = build_earl_document(_request())

    assert document["@graph"] == []


# --- SARIF projection is a pure mechanical transform ---

def test_sarif_result_reuses_the_earl_findings_level_with_no_remapping(monkeypatch):
    """ADR-0011 point 1's own design: severity defaults at the rule level,
    so the SARIF export needs no remapping - just read the override (or
    default) EARL already carried."""
    monkeypatch.setattr("generators.usability_act.build_findings", lambda request: [_finding(severity="low")])

    earl_document = build_earl_document(_request())
    sarif_document = build_sarif_document(earl_document, build_rule_catalog())

    result = sarif_document["runs"][0]["results"][0]
    assert result["level"] == earl_document["@graph"][0]["level"] == "note"
    assert result["ruleId"] == earl_document["@graph"][0]["test"]["@id"]
    assert result["message"]["text"] == earl_document["@graph"][0]["result"]["description"]


def test_sarif_document_lists_every_catalog_rule_regardless_of_findings():
    sarif_document = build_sarif_document({"@graph": []}, build_rule_catalog())

    assert len(sarif_document["runs"][0]["tool"]["driver"]["rules"]) == len(_RULE_CATALOG)
    assert sarif_document["runs"][0]["results"] == []


# --- the registered document ---

def test_generate_returns_all_four_outputs():
    outputs = UsabilityDocument().outputs(_request())

    assert [o.filename for o in outputs] == ["usability-rules", "usability.earl", "usability.sarif", "usability"]
    assert [(o.kind, o.extension) for o in outputs] == [
        ("rule-catalog", "json"), ("source", "jsonld"), ("projection", "json"), ("view", "md"),
    ]
    json.loads(outputs[0].content)
    json.loads(outputs[1].content)
    json.loads(outputs[2].content)


def test_the_view_says_what_it_did_not_check_when_no_findings():
    view = UsabilityDocument().outputs(_request())[3].content

    assert "narrow statement" in view
