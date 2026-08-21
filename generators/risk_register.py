"""`risk-register.json` - structurally-observable risk flags on
`architecture.cyclonedx.json`'s third-party services, docs/adr/0024.

**Deterministic, no live CVE lookup** (ADR-0024 point 1). A real CVE
database cross-reference (OSV, NVD, or similar) would be the first
exception to the determinism every Short hash ID in this map depends on
(same crawl in, same output out) - reserved rather than built, the same
posture `coverage.json` took on `roles`/`blockers` it couldn't observe
honestly (ADR-0001).

**One real v1 rule: known information-disclosure header names.**
`architecture_cyclonedx.py`'s own `DISCLOSED_HEADERS_PROPERTY` is a
reserved CycloneDX property - this crawl captures no HTTP response
headers at all yet, so it is always empty in a real run today. The
detection logic itself is real and tested against a fixture (this
module never fabricates a finding from data that doesn't exist): once a
future header-capture pass populates that property, this document
starts reporting for real, with no change to this module. `_HEADER_NAMES`
is a small, well-established list (OWASP's own "Information Exposure
Through HTTP Headers" guidance names the same set) - a header's mere
*name* being present is the risk signal (implementation detail
disclosure), never its value, so no maintained version/EOL database is
needed the way "outdated version strings" (ADR-0024's other named
example) would require - deliberately not attempted here, since pragma
has no version-string capture to check one against either.

**SARIF `level` always populated, native CVSS only when a real CVE is
cross-referenced** (ADR-0024 point 2). `cvss_score`/`cvss_vector` are
genuinely absent - not present with a `null` value - since v1 never
cross-references a real CVE; they exist in the schema for the day a
future ticket wires live lookup in, matching `accessibility`'s own
`impact`-rides-alongside-`level` precedent (ADR-0012).

**Sparse annotation, never a re-listing** (ADR-0024 point 3). Each entry
cites `architecture.cyclonedx.json`'s own `externalServices[].name` by
reference (`service`) - the full third-party inventory is never
duplicated here.

Details: docs/dev/generators/risk_register.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .architecture_cyclonedx import DISCLOSED_HEADERS_PROPERTY, build_cyclonedx_document

_SCHEMA_PATH = "schemas/risk-register.schema.json"

# OWASP's own "Information Exposure Through HTTP Headers" list - a
# header's presence discloses implementation detail regardless of its
# value, so no version-comparison logic is needed to flag it.
_DISCLOSURE_HEADER_NAMES = ("Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version", "X-Generator")

_DISCLOSURE_RULE = "information-disclosure-header"


def _service_property(service: Dict[str, Any], name: str) -> str:
    for prop in service.get("properties", []):
        if prop.get("name") == name:
            return prop.get("value", "")
    return ""


def _disclosed_headers(service: Dict[str, Any]) -> Tuple[str, ...]:
    """The comma-separated `DISCLOSED_HEADERS_PROPERTY` value, split and
    stripped - empty for every service until a future header-capture
    pass populates it.
    Details: docs/dev/generators/risk_register.md#_disclosed_headers
    """
    raw = _service_property(service, DISCLOSED_HEADERS_PROPERTY)
    return tuple(header.strip() for header in raw.split(",") if header.strip())


def _disclosure_entry(service_name: str, header: str) -> Dict[str, Any]:
    return {
        "service": service_name,
        "rule": _DISCLOSURE_RULE,
        "description": f"{service_name} discloses implementation detail via the '{header}' response header.",
        "level": "warning",
    }


def detect_structural_risks(cyclonedx_document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every structurally-observable risk flag across
    `cyclonedx_document["externalServices"]` - deterministic, no network
    call, real for whatever evidence this crawl actually captured.
    Details: docs/dev/generators/risk_register.md#detect_structural_risks
    """
    entries: List[Dict[str, Any]] = []
    for service in cyclonedx_document.get("externalServices", []):
        for header in _disclosed_headers(service):
            if header in _DISCLOSURE_HEADER_NAMES:
                entries.append(_disclosure_entry(service["name"], header))
    return entries


def build_risk_register(request: DocumentRequest) -> List[Dict[str, Any]]:
    """`risk-register.json` - recomputes `architecture.cyclonedx.json`'s
    own document directly from the graph rather than reading a file
    `architecture` may not have written this run, the same "call the
    real build function" discipline every cross-generator call in this
    map already follows.
    Details: docs/dev/generators/risk_register.md#build_risk_register
    """
    cyclonedx_document = build_cyclonedx_document(request.graph_store.integrations())
    return detect_structural_risks(cyclonedx_document)


def _render_risk_register_view(entries: List[Dict[str, Any]]) -> str:
    """`risk-register.md` - mechanically rendered from `risk-register.json`.
    Details: docs/dev/generators/risk_register.md#_render_risk_register_view
    """
    lines = ["# Risk Register", ""]
    if not entries:
        lines.append(
            "No structurally-observable risk was flagged. Read that narrowly: live CVE "
            "cross-referencing is reserved, not built (ADR-0024) - an empty register means no "
            "known information-disclosure header was observed, not that the third-party services "
            "this crawl integrates with carry no risk at all."
        )
        return "\n".join(lines) + "\n"

    lines += ["| Service | Rule | Level | Description |", "|---|---|---|---|"]
    lines += [
        f"| {entry['service']} | {entry['rule']} | {entry['level']} | {entry['description']} |"
        for entry in entries
    ]
    lines.append("")
    return "\n".join(lines)


def _as_json(entries: List[Dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("risk-register")
class RiskRegisterDocument(DocumentGenerator):
    """`risk-register.json` (source, schema-validated) and
    `risk-register.md` (view) - docs/adr/0024.
    Details: docs/dev/generators/risk_register.md#riskregisterdocument
    """

    name = "risk-register"
    title = "Risk Register"
    purpose = "Structurally-observable risk flags on architecture.cyclonedx.json's third-party services, by reference."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        entries = build_risk_register(request)
        validate_against_schema(entries, _SCHEMA_PATH)
        view = _render_risk_register_view(entries)
        return (
            DocumentOutput(filename="risk-register", kind="source", extension="json", content=_as_json(entries)),
            DocumentOutput(filename="risk-register", kind="view", extension="md", content=view),
        )
