"""Unit tests for generators/risk_register.py - structurally-observable
risk flags on architecture.cyclonedx.json's third-party services
(docs/adr/0024)."""
from core.documents import DocumentRequest
from generators.risk_register import (
    RiskRegisterDocument,
    build_risk_register,
    detect_structural_risks,
)
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/risk-register.schema.json"


def _cyclonedx_document(*services):
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "externalServices": list(services)}


def _service(name, disclosed_headers=""):
    return {
        "provider": {"name": name}, "endpoint": [f"https://{name}"], "name": name,
        "description": "", "properties": [{"name": "pragma:evidence:disclosedHeaders", "value": disclosed_headers}],
    }


class _Store:
    def __init__(self, integrations):
        self._integrations = integrations

    def integrations(self):
        return self._integrations


def _request(integrations):
    return DocumentRequest(graph_store=_Store(integrations), site="shop.example", agent=None)


# --- detect_structural_risks ---

def test_a_known_disclosure_header_produces_one_flag():
    document = _cyclonedx_document(_service("cdn.example.com", disclosed_headers="X-Powered-By"))

    entries = detect_structural_risks(document)

    assert len(entries) == 1
    assert entries[0]["service"] == "cdn.example.com"
    assert entries[0]["rule"] == "information-disclosure-header"


def test_an_unknown_header_name_is_not_flagged():
    """Not every header is a risk - only the small, well-established
    information-disclosure set."""
    document = _cyclonedx_document(_service("cdn.example.com", disclosed_headers="X-Request-Id"))

    assert detect_structural_risks(document) == []


def test_no_disclosed_headers_property_produces_no_flag_not_an_error():
    document = _cyclonedx_document(_service("cdn.example.com"))

    assert detect_structural_risks(document) == []


def test_an_empty_third_party_inventory_produces_an_empty_register():
    assert detect_structural_risks(_cyclonedx_document()) == []


def test_multiple_disclosed_headers_on_one_service_each_produce_their_own_entry():
    document = _cyclonedx_document(_service("cdn.example.com", disclosed_headers="Server, X-Powered-By"))

    entries = detect_structural_risks(document)

    assert len(entries) == 2
    assert {entry["description"].split("'")[1] for entry in entries} == {"Server", "X-Powered-By"}


def test_level_is_always_populated():
    document = _cyclonedx_document(_service("cdn.example.com", disclosed_headers="Server"))

    assert detect_structural_risks(document)[0]["level"] in ("error", "warning", "note", "none")


def test_cvss_score_is_absent_not_null_since_no_cve_is_ever_cross_referenced():
    document = _cyclonedx_document(_service("cdn.example.com", disclosed_headers="Server"))

    entry = detect_structural_risks(document)[0]
    assert "cvss_score" not in entry
    assert "cvss_vector" not in entry


# --- build_risk_register ---

def test_build_risk_register_reads_real_integrations_off_the_store():
    integrations = [{"host": "cdn.example.com", "method": "GET", "path_pattern": "/lib.js", "call_count": 3}]

    entries = build_risk_register(_request(integrations))

    # No disclosed-header capture exists in this crawl yet - honestly empty.
    assert entries == []


# --- the document ---

def test_generate_returns_a_source_and_a_view_output():
    outputs = RiskRegisterDocument().outputs(_request([]))

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_an_empty_register_states_the_reserved_cve_lookup_gap():
    view = RiskRegisterDocument().outputs(_request([]))[1].content

    assert "reserved" in view


def test_the_document_validates_against_its_own_schema():
    entries = build_risk_register(_request([]))

    validate_against_schema(entries, _SCHEMA_PATH)
