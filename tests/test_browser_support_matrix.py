"""Unit tests for generators/browser_support_matrix.py - the evidence/
query/business-reason entry shape, real and tested against synthetic
fixtures even though no capture instrumentation populates it yet
(docs/adr/0028)."""
import pytest

from core.registry import DOCUMENT_REGISTRY
from generators.browser_support_matrix import (
    BrowserSupportMatrixDocument,
    TechnicalEvidence,
    build_browser_support_matrix,
    ua_sniff_query,
    vendor_prefix_query,
)
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/browser-support-matrix.schema.json"


# --- vendor_prefix_query ---

def test_a_webkit_prefix_maps_to_safari():
    assert vendor_prefix_query("-webkit-transform") == "safari"


def test_an_ms_prefix_maps_to_ie():
    assert vendor_prefix_query("-ms-flexbox") == "ie"


def test_an_unprefixed_property_maps_to_nothing():
    assert vendor_prefix_query("transform") is None


# --- ua_sniff_query ---

def test_a_known_ie_signature_maps_to_ie():
    assert ua_sniff_query("Trident") == "ie"
    assert ua_sniff_query("MSIE") == "ie"


def test_an_unrecognized_substring_maps_to_nothing():
    assert ua_sniff_query("SomeUnknownEngine") is None


# --- build_browser_support_matrix ---

def test_a_polyfill_observation_produces_one_entry_with_no_query():
    """A polyfill's mere presence targets an unspecified range of older
    browsers - the evidence alone doesn't determine a specific query."""
    evidence = [TechnicalEvidence(kind="polyfill", subject="es5-shim")]

    entries = build_browser_support_matrix(evidence)

    assert len(entries) == 1
    assert entries[0]["kind"] == "polyfill"
    assert entries[0]["subject"] == "es5-shim"
    assert entries[0]["browserslist_query"] is None


def test_a_vendor_prefixed_rule_produces_one_entry_with_its_inferred_query():
    evidence = [TechnicalEvidence(kind="vendor_prefix", subject="-ms-flexbox", browserslist_query=vendor_prefix_query("-ms-flexbox"))]

    entries = build_browser_support_matrix(evidence)

    assert entries[0]["kind"] == "vendor_prefix"
    assert entries[0]["browserslist_query"] == "ie"


def test_business_reason_always_defaults_to_unset():
    """Nothing here is inferable from the site - only a human review
    pass fills this in (ADR-0028 point 1)."""
    evidence = [TechnicalEvidence(kind="ua_sniffing", subject="Trident", browserslist_query="ie")]

    entries = build_browser_support_matrix(evidence)

    assert entries[0]["business_reason"] is None


def test_performance_baseline_refs_cite_by_reference_not_duplicated_data():
    evidence = [TechnicalEvidence(kind="vendor_prefix", subject="-ms-grid", performance_baseline_refs=("t-abc123",))]

    entries = build_browser_support_matrix(evidence)

    assert entries[0]["performance_baseline_refs"] == ["t-abc123"]


def test_no_evidence_produces_an_empty_matrix_not_an_error():
    assert build_browser_support_matrix([]) == []


def test_the_document_validates_against_its_own_schema():
    evidence = [
        TechnicalEvidence(kind="polyfill", subject="es5-shim"),
        TechnicalEvidence(kind="vendor_prefix", subject="-ms-flexbox", browserslist_query="ie"),
    ]

    entries = build_browser_support_matrix(evidence)

    validate_against_schema(entries, _SCHEMA_PATH)


def test_an_empty_matrix_is_still_structurally_valid():
    validate_against_schema(build_browser_support_matrix([]), _SCHEMA_PATH)


# --- the registered document (ADR-0028) ---

def test_browser_support_matrix_is_registered_so_manifest_can_enumerate_it():
    assert "browser-support-matrix" in DOCUMENT_REGISTRY.names()


def test_generate_raises_rather_than_returning_an_empty_document():
    """No partial document is worth reserving a field on here either -
    the same posture asyncapi.json/i18n-inventory.json already
    established."""
    with pytest.raises(NotImplementedError):
        BrowserSupportMatrixDocument().generate(request=None)
