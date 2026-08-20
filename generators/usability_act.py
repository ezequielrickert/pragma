"""`usability-rules.json` + `usability.earl.jsonld` + `usability.sarif.json`
+ `usability.md`, per docs/adr/0011 - ACT Rules Format 1.1 rule catalog,
EARL 1.0/JSON-LD findings, a mechanical SARIF projection, and a view
rendered from both.

Serialization only: every finding still comes from
`generators/usability.py`'s deterministic detection rules, unchanged -
the same `build_X`/adapter split every other generator here uses.

Details: docs/dev/generators/usability_act.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .usability import Finding, build_findings

_RULES_SCHEMA_PATH = "schemas/usability-rules.schema.json"
_EARL_SCHEMA_PATH = "schemas/usability.earl.schema.json"
_SARIF_SCHEMA_PATH = "schemas/usability.sarif.schema.json"

# EARL's own, real, long-established namespace - not one of this
# pipeline's own schema-locked `https://pragma.local/...` identifiers.
_EARL_CONTEXT = "https://www.w3.org/ns/earl"

# usability.py's own severity vocabulary -> SARIF 2.1.0's level enum
# (ADR-0011 point 1 - the only spec-native severity field across
# ACT/EARL/WCAG-EM/SARIF).
_SEVERITY_TO_LEVEL: Dict[str, str] = {"high": "error", "medium": "warning", "low": "note"}


@dataclass(frozen=True)
class RuleDefinition:
    """One hand-authored rule (ADR-0011 point 4) - `CONTEXT.md`'s Rule
    catalog: fixed for a rule-set version, not derived from any crawl.
    Details: docs/dev/generators/usability_act.md#ruledefinition
    """

    id: str
    description: str
    nielsen_heuristic: str
    level: str


# One entry per distinct Finding.rule usability.py's detection functions
# can produce - RULE-<heuristic-slug>-<NN> (ADR-0011 point 2), sequential
# per heuristic. A sixth detection rule appearing in build_findings with
# no catalog entry here is a real bug this module's own tests catch.
_RULE_CATALOG: Tuple[RuleDefinition, ...] = (
    RuleDefinition(
        id="RULE-consistency-and-standards-01", nielsen_heuristic="consistency-and-standards", level="warning",
        description="The same component family renders in more than one background colour.",
    ),
    RuleDefinition(
        id="RULE-consistency-and-standards-02", nielsen_heuristic="consistency-and-standards", level="warning",
        description="One endpoint is triggered by controls labelled two different ways.",
    ),
    RuleDefinition(
        id="RULE-error-prevention-01", nielsen_heuristic="error-prevention", level="warning",
        description="A field named or labelled for a specific input type is declared as plain text.",
    ),
    RuleDefinition(
        id="RULE-help-users-recognize-diagnose-and-recover-from-errors-01",
        nielsen_heuristic="help-users-recognize-diagnose-and-recover-from-errors", level="note",
        description="A disabled control has no nearby text explaining why.",
    ),
    RuleDefinition(
        id="RULE-user-control-and-freedom-01", nielsen_heuristic="user-control-and-freedom", level="warning",
        description="No interaction the crawl tried led anywhere from this screen.",
    ),
)

_RULE_ID_BY_FINDING_RULE: Dict[str, str] = {
    "inconsistent-family-styling": "RULE-consistency-and-standards-01",
    "inconsistent-action-naming": "RULE-consistency-and-standards-02",
    "missing-semantic-input-type": "RULE-error-prevention-01",
    "unexplained-disabled-control": "RULE-help-users-recognize-diagnose-and-recover-from-errors-01",
    "dead-end-screen": "RULE-user-control-and-freedom-01",
}


def build_rule_catalog() -> Dict[str, Any]:
    """`usability-rules.json` - hand-authored, fixed for this rule-set
    version, never derived from a crawl.
    Details: docs/dev/generators/usability_act.md#build_rule_catalog
    """
    return {
        "rules": [
            {
                "id": rule.id, "description": rule.description,
                "x-nielsen-heuristic": rule.nielsen_heuristic,
                "defaultConfiguration": {"level": rule.level},
            }
            for rule in _RULE_CATALOG
        ]
    }


def _earl_assertion(finding: Finding, run_id: str) -> Dict[str, Any]:
    return {
        "@type": "Assertion",
        "test": {"@id": _RULE_ID_BY_FINDING_RULE[finding.rule]},
        "subject": {"@id": finding.where},
        "result": {"@type": "TestResult", "outcome": "earl:failed", "description": finding.detail},
        # Every rule here is a deterministic pattern/heuristic detection -
        # earl:semiAuto/earl:manual are reserved for an LLM-flagged or
        # HITL-confirmed finding, neither of which exists yet (ADR-0011
        # point 3).
        "mode": "earl:automatic",
        "level": _SEVERITY_TO_LEVEL.get(finding.severity, "warning"),
        # Reserved: no stable per-interaction/HAR/screenshot id scheme
        # exists yet (the same gap prd/catalog/data-model left reserved).
        "derived_from": [],
        "coverage_ref": {"run_id": run_id},
        # Reserved: correlating a finding's component to one specific
        # tree.axtree.json node needs a dedicated correlation pass this
        # ticket doesn't build (the same gap catalog.json's
        # x-region.axtree_ref left reserved, ticket #101).
        "axtree_ref": None,
    }


def build_earl_document(request: DocumentRequest) -> Dict[str, Any]:
    """`usability.earl.jsonld` - the real per-run source document, one
    Assertion per finding `usability.py::build_findings` produced.
    Details: docs/dev/generators/usability_act.md#build_earl_document
    """
    run_id = request.settings.get("run_id", "")
    findings = build_findings(request)
    return {"@context": _EARL_CONTEXT, "@graph": [_earl_assertion(finding, run_id) for finding in findings]}


def _sarif_result(assertion: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ruleId": assertion["test"]["@id"],
        "level": assertion["level"],
        "message": {"text": assertion["result"]["description"]},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": assertion["subject"]["@id"]}}}],
    }


def build_sarif_document(earl_document: Dict[str, Any], rule_catalog: Dict[str, Any]) -> Dict[str, Any]:
    """`usability.sarif.json` - a pure mechanical projection of
    `usability.earl.jsonld`'s findings (ADR-0011 point 4): `ruleId`/
    `level`/`message`/`location` read straight off each Assertion, no
    remapping - the point of ADR-0011 point 1's own "severity defaults
    at the rule level... the export needs no remapping" design.
    Details: docs/dev/generators/usability_act.md#build_sarif_document
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


def _finding_row(rules_by_id: Dict[str, Any], assertion: Dict[str, Any]) -> str:
    rule = rules_by_id.get(assertion["test"]["@id"], {})
    return (
        f"| {assertion['level']} | `{assertion['test']['@id']}` | {rule.get('x-nielsen-heuristic', '-')} "
        f"| {assertion['subject']['@id']} | {assertion['result']['description']} |"
    )


def _render_usability_view(rule_catalog: Dict[str, Any], earl_document: Dict[str, Any], site: str) -> str:
    """`usability.md` - mechanically rendered from `usability-rules.json`
    and `usability.earl.jsonld`, never hand-authored in parallel.
    Details: docs/dev/generators/usability_act.md#_render_usability_view
    """
    lines = [f"# Usability Audit: {site}", ""]
    findings = earl_document["@graph"]
    if not findings:
        lines.append(
            "No findings from the deterministic rules. That is a narrow statement: these rules "
            "cover consistency, error prevention and flow structure, not whether the application "
            "is pleasant to use."
        )
        return "\n".join(lines) + "\n"

    rules_by_id = {rule["id"]: rule for rule in rule_catalog["rules"]}
    lines += [
        f"{len(findings)} finding(s) against {len(rule_catalog['rules'])} deterministic rule(s), each "
        "citing the page and element it came from - disagree and go look.",
        "",
        "Not covered here and waiting on richer capture: loading indicators during a request, and "
        "whether a failed submit actually told the user. Both need the DOM observed *during* an "
        "interaction, which the crawl does not do.",
        "",
        "| Level | Rule | Heuristic | Where | Finding |", "|---|---|---|---|---|",
    ]
    lines += [_finding_row(rules_by_id, assertion) for assertion in findings]
    lines.append("")
    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("usability")
class UsabilityDocument(DocumentGenerator):
    """Four outputs: `usability-rules.json` (`kind="rule-catalog"`),
    `usability.earl.jsonld` (`kind="source"`), `usability.sarif.json`
    (`kind="projection"` - `CONTEXT.md`'s reshaping-into-an-external-
    standard sense), and `usability.md` (`kind="view"`).
    Details: docs/dev/generators/usability_act.md#usabilitydocument
    """

    name = "usability"
    title = "Usability Audit"
    purpose = "Nielsen-heuristic findings as an ACT rule catalog + EARL/JSON-LD, with a mechanical SARIF export."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        rule_catalog = build_rule_catalog()
        validate_against_schema(rule_catalog, _RULES_SCHEMA_PATH)

        earl_document = build_earl_document(request)
        validate_against_schema(earl_document, _EARL_SCHEMA_PATH)

        sarif_document = build_sarif_document(earl_document, rule_catalog)
        validate_against_schema(sarif_document, _SARIF_SCHEMA_PATH)

        view = _render_usability_view(rule_catalog, earl_document, request.site)
        return (
            DocumentOutput(
                filename="usability-rules", kind="rule-catalog", extension="json", content=_as_json(rule_catalog)
            ),
            DocumentOutput(
                filename="usability.earl", kind="source", extension="jsonld", content=_as_json(earl_document)
            ),
            DocumentOutput(
                filename="usability.sarif", kind="projection", extension="json", content=_as_json(sarif_document)
            ),
            DocumentOutput(filename="usability", kind="view", extension="md", content=view),
        )
