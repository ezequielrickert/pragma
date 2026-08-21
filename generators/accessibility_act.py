"""`accessibility-rules.json` + `accessibility.earl.jsonld` + `accessibility.sarif.json`
+ `accessibility.md`, per docs/adr/0012 - a rule catalog extracted from real
axe-core rule metadata, EARL 1.0/JSON-LD findings, a mechanical SARIF
projection, and a migration-checklist view. The same `build_X`/adapter split
`usability`/`usability_act` established (docs/adr/0011).

**The rule catalog is real axe-core 4.10.2 data, extracted once, not a live
detection pass.** `generators/axe_core_rules.json` was produced by
loading axe-core 4.10.2's own bundle (`axe.min.js`, retrieved from this
repo's history at the commit before "Pin ladybug; delete the measurement
pass" removed it - the exact version this project last shipped) in a bare
Node context and calling `axe.getRules()` / reading `axe._audit.rules` for
each rule's own default `impact`. No axe-core dependency, network call, or
browser is needed at generation time - the catalog is a checked-in snapshot,
matching `CONTEXT.md`'s Rule catalog definition ("extracted-once").

**The findings are still this crawl's own two deterministic checks**
(`generators/accessibility.py`'s `name_findings`/`landmark_findings`), not a
live axe-core run - that measurement pass was deliberately removed and
resurrecting it is out of this ticket's scope (a `wayfinder:task` execution
ticket, not an architecture reversal). Each finding is promoted into
`accessibility.earl.jsonld` only where it correlates to one specific,
unambiguous real axe-core rule id (`_axe_rule_id`); a finding axe-core has no
matching rule for - ARIA `tab` naming is the one gap in this crawl's own
rule surface - is excluded, and the exclusion is counted, the same
"state the blind spot" discipline `accessibility.py`'s own pointer-layer
skip count already uses.

Details: docs/dev/generators/accessibility_act.md#module
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .accessibility import AccessibilityFinding, build_findings

_RULES_DATA_PATH = "generators/axe_core_rules.json"
_RULES_SCHEMA_PATH = "schemas/accessibility-rules.schema.json"
_EARL_SCHEMA_PATH = "schemas/accessibility.earl.schema.json"
_SARIF_SCHEMA_PATH = "schemas/accessibility.sarif.schema.json"

# EARL's own, real, long-established namespace - not one of this pipeline's
# own schema-locked "https://pragma.local/..." identifiers.
_EARL_CONTEXT = "https://www.w3.org/ns/earl"

# axe-core's own impact vocabulary -> SARIF 2.1.0's level enum (docs/adr/0012
# point 3). critical and serious both collapse to "error": axe-core's own
# docs group them as "must fix", the same must-fix/nice-to-have split every
# other level split in this pipeline draws at one boundary.
_IMPACT_TO_LEVEL: Dict[str, str] = {
    "critical": "error", "serious": "error", "moderate": "warning", "minor": "note",
}

# `AccessibilityFinding.axe_hint` (a `_NAMED_COMPONENT_TYPES` prefix) -> the
# real axe-core rule that checks that control type's accessible name.
# axe-core splits name-checking per element/role rather than offering one
# generic rule, so this table is a real, verified correspondence per type,
# not a guess - each id is confirmed present in `axe_core_rules.json`.
# "tab" has no entry: axe-core 4.10.2 has no rule for ARIA tab naming, and a
# name finding on a tab-type control is excluded rather than mis-cited.
_AXE_RULE_BY_COMPONENT_TYPE: Dict[str, str] = {
    "button": "button-name",
    "submit button": "input-button-name",
    "link": "link-name",
    "checkbox": "label",
    "radio button": "label",
    "toggle switch": "aria-toggle-field-name",
    "native dropdown (select)": "select-name",
    "combobox": "aria-input-field-name",
    "text field": "label",
}

# `AccessibilityFinding.axe_hint` (the specific landmark role) -> the real
# axe-core rule for a duplicate of that role, per docs/adr/0012 point 1.
_AXE_RULE_BY_DUPLICATE_LANDMARK: Dict[str, str] = {
    "banner": "landmark-no-duplicate-banner",
    "main": "landmark-no-duplicate-main",
    "contentinfo": "landmark-no-duplicate-contentinfo",
}


def _load_rule_catalog_data() -> List[Dict[str, Any]]:
    """The raw, checked-in axe-core extraction - `id`/`description`/`help`/
    `helpUrl`/`wcag_tags`/`act_id`/`impact` per rule, 104 rules as of
    axe-core 4.10.2.
    Details: docs/dev/generators/accessibility_act.md#_load_rule_catalog_data
    """
    return json.loads(Path(_RULES_DATA_PATH).read_text(encoding="utf-8"))


def build_rule_catalog() -> Dict[str, Any]:
    """`accessibility-rules.json` - axe-core's own rule set, extracted once
    (docs/adr/0012 point 1), never a hand-authored subset.
    Details: docs/dev/generators/accessibility_act.md#build_rule_catalog
    """
    return {
        "rules": [
            {
                "id": rule["id"],
                "description": rule["description"],
                "help": rule["help"],
                "helpUrl": rule["helpUrl"],
                "accessibility_requirements": rule["wcag_tags"],
                "act_id": rule["act_id"],
                "defaultConfiguration": {
                    "level": _IMPACT_TO_LEVEL[rule["impact"]],
                    "impact": rule["impact"],
                },
            }
            for rule in _load_rule_catalog_data()
        ]
    }


def _axe_rule_id(finding: AccessibilityFinding) -> Optional[str]:
    """The real axe-core rule id this finding corresponds to, or `None` when
    axe-core has no matching rule (excluded from EARL/SARIF, not mis-cited).
    Details: docs/dev/generators/accessibility_act.md#_axe_rule_id
    """
    if finding.rule == "no-main-landmark":
        return "landmark-one-main"
    if finding.rule == "duplicate-unique-landmark":
        return _AXE_RULE_BY_DUPLICATE_LANDMARK.get(finding.axe_hint)
    if finding.rule in ("missing-accessible-name", "placeholder-as-only-label"):
        return _AXE_RULE_BY_COMPONENT_TYPE.get(finding.axe_hint)
    return None


def _earl_assertion(finding: AccessibilityFinding, rule: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    return {
        "@type": "Assertion",
        "test": {"@id": rule["id"]},
        "subject": {"@id": finding.where},
        "result": {"@type": "TestResult", "outcome": "earl:failed", "description": finding.detail},
        # Every rule here is a deterministic pattern detection, not a live
        # axe-core run or an LLM/HITL judgement - earl:semiAuto/earl:manual
        # are reserved for those (docs/adr/0011 point 3, reused here).
        "mode": "earl:automatic",
        "level": _IMPACT_TO_LEVEL[rule["impact"]],
        "impact": rule["impact"],
        # Reserved: no stable per-interaction/HAR/screenshot id scheme
        # exists yet (the same gap prd/catalog/data-model/usability left
        # reserved).
        "derived_from": [],
        "coverage_ref": {"run_id": run_id},
        # Reserved: correlating a finding's component to one specific
        # tree.axtree.json node needs a dedicated correlation pass this
        # ticket doesn't build (the same gap usability.earl.jsonld left
        # reserved, ticket #105).
        "axtree_ref": None,
    }


def build_earl_document(request: DocumentRequest) -> Dict[str, Any]:
    """`accessibility.earl.jsonld` - one Assertion per finding that
    correlates to a real axe-core rule id. A finding axe-core has no rule
    for is silently excluded here and counted by the caller instead - see
    `AccessibilityDocument.generate`.
    Details: docs/dev/generators/accessibility_act.md#build_earl_document
    """
    run_id = request.settings.get("run_id", "")
    findings, _skipped = build_findings(request)
    rules_by_id = {rule["id"]: rule for rule in _load_rule_catalog_data()}

    assertions = []
    for finding in findings:
        rule_id = _axe_rule_id(finding)
        if rule_id is None:
            continue
        assertions.append(_earl_assertion(finding, rules_by_id[rule_id], run_id))
    return {"@context": _EARL_CONTEXT, "@graph": assertions}


def _sarif_result(assertion: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ruleId": assertion["test"]["@id"],
        "level": assertion["level"],
        "message": {"text": assertion["result"]["description"]},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": assertion["subject"]["@id"]}}}],
    }


def build_sarif_document(earl_document: Dict[str, Any], rule_catalog: Dict[str, Any]) -> Dict[str, Any]:
    """`accessibility.sarif.json` - a pure mechanical projection of
    `accessibility.earl.jsonld`'s findings (docs/adr/0012 point 5, same
    "no remapping" design as `usability.sarif.json`, docs/adr/0011 point 4):
    `ruleId`/`level`/`message`/`location` read straight off each Assertion.
    Details: docs/dev/generators/accessibility_act.md#build_sarif_document
    """
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pragma",
                        "rules": [{"id": rule["id"]} for rule in rule_catalog["rules"]],
                    }
                },
                "results": [_sarif_result(assertion) for assertion in earl_document["@graph"]],
            }
        ],
    }


def _screen(subject_id: str) -> str:
    """The page portion of an assertion's `subject.@id` - `where` is either
    a bare page url (landmark findings) or `"{page_url} — {path}"` (name
    findings); either way the page is the part before the first ` — `.
    Details: docs/dev/generators/accessibility_act.md#_screen
    """
    return subject_id.split(" — ", 1)[0]


def _checklist_row(rules_by_id: Dict[str, Any], rule_id: str, assertions: List[Dict[str, Any]]) -> str:
    rule = rules_by_id.get(rule_id, {})
    screens = sorted({_screen(assertion["subject"]["@id"]) for assertion in assertions})
    level = assertions[0]["level"]
    return (
        f"| {level} | `{rule_id}` | {rule.get('help', '-')} | {len(assertions)} | "
        f"{', '.join(screens)} |"
    )


def _exclusion_note(excluded: int) -> List[str]:
    """The "some findings have no axe-core rule" note, or `[]` when nothing
    was excluded - shared by both branches of `_render_accessibility_view`
    so the wording can't drift between them.
    Details: docs/dev/generators/accessibility_act.md#_exclusion_note
    """
    if not excluded:
        return []
    return [
        f"{excluded} finding(s) from this crawl's own checks have no matching axe-core rule "
        "(ARIA tab naming is the one gap in this crawl's rule surface) and are excluded here "
        "rather than mis-cited against the wrong rule.",
        "",
    ]


def _render_accessibility_view(rule_catalog: Dict[str, Any], earl_document: Dict[str, Any], excluded: int, site: str) -> str:
    """`accessibility.md` - the migration checklist itself (docs/adr/0012
    point 4: no separate `checklist.json`), findings deduplicated by rule so
    a reviewer sees "fix `button-name`, 6 instances across 3 screens" once,
    not six separate rows for the same underlying gap.
    Details: docs/dev/generators/accessibility_act.md#_render_accessibility_view
    """
    lines = [f"# Accessibility Audit: {site}", ""]
    findings = earl_document["@graph"]
    if not findings:
        lines.append(
            "No findings from the rules this crawl can check without a live axe-core run: "
            "accessible names and landmark structure. Read that narrowly - a clean report here "
            "does not mean the application is accessible; most of axe-core's ~100 rules need a "
            "measurement pass this pipeline does not have."
        )
        if excluded:
            lines.append("")
            lines += _exclusion_note(excluded)
        return "\n".join(lines) + "\n"

    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for assertion in findings:
        by_rule.setdefault(assertion["test"]["@id"], []).append(assertion)

    rules_by_id = {rule["id"]: rule for rule in rule_catalog["rules"]}
    order = {"error": 0, "warning": 1, "note": 2, "none": 3}
    rule_ids = sorted(by_rule, key=lambda rule_id: (order.get(by_rule[rule_id][0]["level"], 4), rule_id))

    lines += [
        f"{len(findings)} finding(s) against {len(rule_ids)} distinct rule(s) - a migration "
        "checklist, not a per-instance log: fix the rule, not each occurrence.",
        "",
    ]
    lines += _exclusion_note(excluded)
    lines += [
        "Not covered here and waiting on a live axe-core run: everything past accessible names "
        "and landmark structure - contrast, touch targets, focus order, and axe-core's other "
        "~100 rules.",
        "",
        "| Level | Rule | What to fix | Instances | Screens |", "|---|---|---|---|---|",
    ]
    lines += [_checklist_row(rules_by_id, rule_id, by_rule[rule_id]) for rule_id in rule_ids]
    lines.append("")
    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("accessibility")
class AccessibilityDocument(DocumentGenerator):
    """Four outputs: `accessibility-rules.json` (`kind="rule-catalog"`),
    `accessibility.earl.jsonld` (`kind="source"`), `accessibility.sarif.json`
    (`kind="projection"`), and `accessibility.md` (`kind="view"`, doubling
    as the migration checklist per docs/adr/0012 point 4).
    Details: docs/dev/generators/accessibility_act.md#accessibilitydocument
    """

    name = "accessibility"
    title = "Accessibility Audit"
    purpose = "Real axe-core rule catalog + EARL/JSON-LD findings from this crawl's deterministic checks, with a mechanical SARIF export and a migration checklist."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        rule_catalog = build_rule_catalog()
        validate_against_schema(rule_catalog, _RULES_SCHEMA_PATH)

        earl_document = build_earl_document(request)
        validate_against_schema(earl_document, _EARL_SCHEMA_PATH)

        sarif_document = build_sarif_document(earl_document, rule_catalog)
        validate_against_schema(sarif_document, _SARIF_SCHEMA_PATH)

        findings, _skipped = build_findings(request)
        excluded = len(findings) - len(earl_document["@graph"])
        view = _render_accessibility_view(rule_catalog, earl_document, excluded, request.site)
        return (
            DocumentOutput(
                filename="accessibility-rules", kind="rule-catalog", extension="json", content=_as_json(rule_catalog)
            ),
            DocumentOutput(
                filename="accessibility.earl", kind="source", extension="jsonld", content=_as_json(earl_document)
            ),
            DocumentOutput(
                filename="accessibility.sarif", kind="projection", extension="json", content=_as_json(sarif_document)
            ),
            DocumentOutput(filename="accessibility", kind="view", extension="md", content=view),
        )
