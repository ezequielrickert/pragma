"""Unit tests for generators/graph_export.py - built directly against
InMemoryGraphStore, no live crawl needed, same convention
tests/test_component_tree.py already established (build_graph_export only
touches GraphStore's read surface)."""
import json

from generators.graph_export import build_graph_export, generate_graph_export_document
from database.memory_graph_store import InMemoryGraphStore

SITE = "export-test-site"


def _store():
    store = InMemoryGraphStore()
    store.connect()
    return store


def test_build_graph_export_includes_page_fields():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished", components=2, title="Home", description="A page")

    export = build_graph_export(store, SITE)

    assert export["site"] == SITE
    assert "generated_at" in export
    page = export["pages"][0]
    assert page["url"] == "example.com"
    assert page["status"] == "Finished"
    assert page["title"] == "Home"
    assert page["description"] == "A page"


def test_build_graph_export_includes_edges_and_ledgers():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")
    store.upsert_page(SITE, "example.com/about", status="Finished")
    store.record_edge(SITE, "example.com", "example.com/about", component="a.about", action="click")
    store.record_component(SITE, "example.com", "a.about", tag="a", text="About")
    store.record_text_content(SITE, "example.com", "p.intro", tag="p", text="Welcome")

    export = build_graph_export(store, SITE)

    assert export["edges"] == [
        {"from": "example.com", "component": "a.about", "action": "click", "to": "example.com/about"}
    ]
    assert export["component_ledger"]["example.com"]["a.about"]["text"] == "About"
    assert export["text_content_ledger"]["example.com"][0]["text"] == "Welcome"


def test_generate_graph_export_document_is_valid_deterministic_json():
    store = _store()
    store.upsert_page(SITE, "example.com", status="Finished")

    doc1 = generate_graph_export_document(store, SITE)
    parsed = json.loads(doc1)
    assert parsed["site"] == SITE

    # Same underlying data, generated_at aside - key ordering must be stable
    # (sort_keys=True) so re-exporting an unchanged graph diffs cleanly.
    import re

    strip_timestamp = lambda s: re.sub(r'"generated_at": "[^"]*"', '"generated_at": ""', s)
    doc2 = generate_graph_export_document(store, SITE)
    assert strip_timestamp(doc1) == strip_timestamp(doc2)
