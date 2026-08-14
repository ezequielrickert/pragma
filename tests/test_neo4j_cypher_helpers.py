"""Unit tests for the shared Cypher-fragment helpers in
database/neo4j_graph_store.py (docs/explicativos/plan-almacenamiento.md
Fase B - "repeated Cypher patterns" finding). Pure string assertions, no
live Neo4j needed - unlike tests/test_neo4j_graph_store_integration.py
(which self-skips without a reachable instance), these run unconditionally
so the refactor that introduced these helpers has real regression coverage
even in an environment with no Neo4j available.
"""
import pytest

neo4j = pytest.importorskip("neo4j")  # only need the driver package importable, not a live server

from database.neo4j_graph_store import _COMPONENT_BLANK_STUB, _page_ensure_clause


def test_page_ensure_clause_defaults_every_field_for_the_given_variable():
    clause = _page_ensure_clause("p", "page_url")
    assert "MERGE (p:Page {site: $site, url: $page_url})" in clause
    assert "p.status = 'Pending'" in clause
    assert "p.components = 0" in clause
    assert "p.context = '-'" in clause
    assert "p.label = '-'" in clause


def test_page_ensure_clause_uses_the_given_variable_and_param_consistently():
    """Every generated field reference must use the same Cypher variable -
    a copy/paste-across-two-endpoints bug (e.g. record_link's `a`/`b`) would
    show up here as a field prefixed with the wrong letter."""
    clause = _page_ensure_clause("a", "from_url")
    assert "$from_url" in clause
    assert "$page_url" not in clause
    for field in ("status", "components", "context", "label"):
        assert f"a.{field}" in clause
    assert "b." not in clause and "p." not in clause


def test_page_ensure_clause_has_balanced_braces_when_embedded():
    """The f-string that builds this fragment must produce literal `{`/`}`
    (Cypher map syntax) via doubled braces, not leak a stray single brace -
    an easy mistake when converting a triple-quoted literal query into an
    f-string. A real syntax error would only surface against a live driver
    connection; this catches the specific failure mode (unbalanced braces)
    without needing one.
    """
    query_text = f"MERGE (s:Site) WITH s {_page_ensure_clause('p', 'page_url')} RETURN p"
    assert query_text.count("{") == query_text.count("}")
    assert "{{" not in query_text and "}}" not in query_text, "no unresolved doubled-brace escapes leaked through"


def test_component_blank_stub_includes_options_uniformly():
    """Fase B unified the three previously-divergent copies (one omitted
    `c.options = ''`) - this must never silently drift back apart."""
    assert "c.options = ''" in _COMPONENT_BLANK_STUB
    assert "c.interacted = false" in _COMPONENT_BLANK_STUB
    # Interactions are :INTERACTED relationships now, not an array property;
    # the counter is what seeds each edge's `seq`.
    assert "c.interaction_count = 0" in _COMPONENT_BLANK_STUB
    assert "c.caption = ''" in _COMPONENT_BLANK_STUB
    assert "c.network_requests = []" in _COMPONENT_BLANK_STUB
    assert query_has_balanced_braces(_COMPONENT_BLANK_STUB)


def query_has_balanced_braces(text: str) -> bool:
    return text.count("{") == text.count("}")
