"""Unit tests for dashboard/renderer_audit.py - the Phase B reuse-audit
verdict table (ADR-0016 point 3, ticket #123)."""
import core.bootstrap  # noqa: F401  (registers every real document)
from core.registry import DOCUMENT_REGISTRY
from dashboard.renderer_audit import RENDERER_BY_NAME, renderer_for

# The only three documents that never produce a file at all -
# ADR-0018/0027/0028's own raise-instead-of-empty posture.
_ALWAYS_ABSENT = {"asyncapi", "i18n-inventory", "browser-support-matrix"}


def test_openapi_is_the_one_document_with_a_dedicated_renderer():
    assert renderer_for("openapi") == "redoc"


def test_every_other_audited_document_defaults_to_generic():
    for name, verdict in RENDERER_BY_NAME.items():
        if name == "openapi":
            continue
        assert verdict == "generic", f"{name} unexpectedly has a dedicated verdict: {verdict}"


def test_an_unaudited_name_defaults_to_generic_not_an_error():
    assert renderer_for("some-future-document") == "generic"


def test_every_document_that_can_ever_produce_a_file_is_covered_by_the_audit():
    """The audit table must not silently miss a real, currently-buildable
    document - only the three that always raise are allowed to be
    absent from it."""
    registered = set(DOCUMENT_REGISTRY.names())
    uncovered = registered - set(RENDERER_BY_NAME) - _ALWAYS_ABSENT

    assert uncovered == set(), f"registered but not in the audit table: {uncovered}"


def test_the_always_absent_documents_are_not_in_the_table_at_all():
    """They aren't 'generic' - no file exists for either renderer to
    ever apply to, a different fact than 'gets the generic template.'"""
    for name in _ALWAYS_ABSENT:
        assert name not in RENDERER_BY_NAME
