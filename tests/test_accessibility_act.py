"""Unit tests for generators/accessibility_act.py - the ACT/EARL/SARIF
serialization layer over accessibility.py's own findings."""
import json

from core.documents import DocumentRequest
from generators.accessibility import AccessibilityFinding
from generators.accessibility_act import (
    AccessibilityDocument,
    _axe_rule_id,
    build_earl_document,
    build_rule_catalog,
    build_sarif_document,
)

PAGE = "https://shop.example/checkout"


class _Store:
    def __init__(self, ledger=None, landmarks=None):
        self._ledger = ledger or {}
        self._landmarks = landmarks or {}

    def get_component_ledger(self):
        return self._ledger

    def get_page_landmarks(self):
        return self._landmarks


def _control(path, component_type="button", text="Comprar", **extra):
    row = {
        "page_url": PAGE, "path": path, "tag": "button", "component_type": component_type,
        "text": text, "label": "", "placeholder": "", "layer": "semantic",
    }
    row.update(extra)
    return row


def _request(ledger=None, landmarks=None, settings=None):
    return DocumentRequest(
        graph_store=_Store(ledger, landmarks), site="shop.example", agent=None, settings=settings or {"run_id": "R1"}
    )


# --- rule catalog ---

def test_the_rule_catalog_is_the_real_extracted_axe_core_set():
    catalog = build_rule_catalog()

    assert len(catalog["rules"]) == 104
    assert all(rule["id"] for rule in catalog["rules"])
    assert all(rule["defaultConfiguration"]["level"] in ("error", "warning", "note", "none") for rule in catalog["rules"])
    assert all(rule["defaultConfiguration"]["impact"] in ("minor", "moderate", "serious", "critical") for rule in catalog["rules"])


def test_a_known_rule_carries_its_real_wcag_tags_and_act_id():
    catalog = build_rule_catalog()
    button_name = next(rule for rule in catalog["rules"] if rule["id"] == "button-name")

    assert "wcag412" in button_name["accessibility_requirements"]
    assert button_name["act_id"]
    assert button_name["defaultConfiguration"] == {"level": "error", "impact": "critical"}


def test_landmark_rules_have_no_wcag_tags_axe_treats_them_as_best_practice():
    catalog = build_rule_catalog()
    landmark_one_main = next(rule for rule in catalog["rules"] if rule["id"] == "landmark-one-main")

    assert landmark_one_main["accessibility_requirements"] == []
    assert landmark_one_main["defaultConfiguration"] == {"level": "warning", "impact": "moderate"}


# --- axe rule correlation ---

def test_every_named_component_type_but_tab_resolves_to_a_real_axe_rule():
    """ARIA tab naming is the one real gap in axe-core's own rule set - see
    the module docstring. Every other operable type accessibility.py tracks
    must resolve, or a finding on it would silently vanish."""
    from generators.accessibility import _NAMED_COMPONENT_TYPES

    for component_type in _NAMED_COMPONENT_TYPES:
        if component_type == "tab":
            continue
        finding = AccessibilityFinding(
            rule="missing-accessible-name", criterion="", severity="high", where="", detail="",
            recommendation="", axe_hint=component_type,
        )
        assert _axe_rule_id(finding) is not None, f"{component_type} has no axe rule mapping"


def test_a_tab_naming_finding_has_no_axe_correlation():
    finding = AccessibilityFinding(
        rule="missing-accessible-name", criterion="", severity="high", where="", detail="",
        recommendation="", axe_hint="tab",
    )

    assert _axe_rule_id(finding) is None


def test_duplicate_landmark_resolves_per_specific_role():
    for role, expected in [
        ("banner", "landmark-no-duplicate-banner"),
        ("main", "landmark-no-duplicate-main"),
        ("contentinfo", "landmark-no-duplicate-contentinfo"),
    ]:
        finding = AccessibilityFinding(
            rule="duplicate-unique-landmark", criterion="", severity="low", where="", detail="",
            recommendation="", axe_hint=role,
        )
        assert _axe_rule_id(finding) == expected


# --- EARL assembly ---

def test_earl_document_has_one_assertion_per_correlated_finding():
    document = build_earl_document(_request(
        ledger={PAGE: {"b#1": _control("b#1", text="")}}, landmarks={PAGE: {"banner": 1}}
    ))

    # missing-accessible-name (button) + no-main-landmark, both correlate
    assert len(document["@graph"]) == 2


def test_earl_assertion_normalizes_impact_to_level_and_keeps_impact_as_provenance():
    document = build_earl_document(_request(ledger={PAGE: {"b#1": _control("b#1", text="")}}))
    assertion = document["@graph"][0]

    assert assertion["test"]["@id"] == "button-name"
    assert assertion["impact"] == "critical"
    assert assertion["level"] == "error"
    assert assertion["mode"] == "earl:automatic"


def test_a_tab_finding_is_excluded_from_the_earl_graph():
    ledger = {PAGE: {"t#1": _control("t#1", component_type="tab", text="")}}

    document = build_earl_document(_request(ledger=ledger))

    assert document["@graph"] == []


def test_earl_assertion_reserved_fields_are_empty_not_invented():
    document = build_earl_document(_request(ledger={PAGE: {"b#1": _control("b#1", text="")}}))
    assertion = document["@graph"][0]

    assert assertion["derived_from"] == []
    assert assertion["axtree_ref"] is None


def test_coverage_ref_carries_the_real_run_id():
    document = build_earl_document(_request(
        ledger={PAGE: {"b#1": _control("b#1", text="")}}, settings={"run_id": "RUN-42"}
    ))

    assert document["@graph"][0]["coverage_ref"]["run_id"] == "RUN-42"


def test_no_findings_is_an_empty_graph_not_an_error():
    document = build_earl_document(_request())

    assert document["@graph"] == []


# --- SARIF projection is a pure mechanical transform ---

def test_sarif_result_reuses_the_earl_findings_level_with_no_remapping():
    earl_document = build_earl_document(_request(ledger={PAGE: {"b#1": _control("b#1", text="")}}))
    sarif_document = build_sarif_document(earl_document, build_rule_catalog())

    result = sarif_document["runs"][0]["results"][0]
    assert result["level"] == earl_document["@graph"][0]["level"] == "error"
    assert result["ruleId"] == earl_document["@graph"][0]["test"]["@id"] == "button-name"
    assert result["message"]["text"] == earl_document["@graph"][0]["result"]["description"]


def test_sarif_document_lists_every_catalog_rule_regardless_of_findings():
    sarif_document = build_sarif_document({"@graph": []}, build_rule_catalog())

    assert len(sarif_document["runs"][0]["tool"]["driver"]["rules"]) == 104
    assert sarif_document["runs"][0]["results"] == []


# --- the registered document ---

def test_generate_returns_all_four_outputs():
    outputs = AccessibilityDocument().outputs(_request(ledger={PAGE: {"b#1": _control("b#1", text="")}}))

    assert [o.filename for o in outputs] == ["accessibility-rules", "accessibility.earl", "accessibility.sarif", "accessibility"]
    assert [(o.kind, o.extension) for o in outputs] == [
        ("rule-catalog", "json"), ("source", "jsonld"), ("projection", "json"), ("view", "md"),
    ]
    json.loads(outputs[0].content)
    json.loads(outputs[1].content)
    json.loads(outputs[2].content)


def test_the_view_says_what_it_did_not_check_when_no_findings():
    view = AccessibilityDocument().outputs(_request())[3].content

    assert "Read that narrowly" in view


def test_the_view_deduplicates_findings_by_rule():
    """Two nameless buttons on different pages are the same underlying gap -
    one checklist row, instance count 2, both screens listed."""
    ledger = {
        "https://shop.example/a": {"b#1": _control("b#1", text="", page_url="https://shop.example/a")},
        "https://shop.example/b": {"b#2": _control("b#2", text="", page_url="https://shop.example/b")},
    }

    view = AccessibilityDocument().outputs(_request(ledger=ledger))[3].content

    assert view.count("`button-name`") == 1
    assert "| error | `button-name` |" in view
    assert "shop.example/a" in view and "shop.example/b" in view


def test_the_view_reports_findings_excluded_for_lacking_an_axe_correlation():
    ledger = {PAGE: {"t#1": _control("t#1", component_type="tab", text="")}}

    view = AccessibilityDocument().outputs(_request(ledger=ledger))[3].content

    assert "1 finding(s)" in view and "no matching axe-core rule" in view
