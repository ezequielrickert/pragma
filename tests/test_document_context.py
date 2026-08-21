"""Unit tests for dashboard/document_context.py - the completeness
guarantee ticket #145 asked for: every registered document has a real
explanation and example, checked by test rather than trusted to stay
in sync (map #142's "don't let this drift the way docs/explicativos/
did" concern)."""
from core import bootstrap  # noqa: F401  (registers the document generators)
from core.registry import DOCUMENT_REGISTRY
from dashboard.document_context import CONTEXT_BY_NAME, context_for


def test_every_registered_document_has_a_real_context_entry():
    missing = [name for name in DOCUMENT_REGISTRY.names() if context_for(name) is None]

    assert not missing, f"documents with no document_context.py entry: {missing}"


def test_every_entry_has_non_empty_explanation_and_example():
    empty = [
        name for name, context in CONTEXT_BY_NAME.items()
        if not context.explanation.strip() or not context.example.strip()
    ]

    assert not empty, f"document_context.py entries with an empty field: {empty}"


def test_an_unregistered_name_returns_none_not_a_placeholder():
    assert context_for("not-a-real-document") is None
