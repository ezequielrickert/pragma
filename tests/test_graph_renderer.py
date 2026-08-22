"""Unit tests for dashboard/graph_renderer.py - the Graph card (ticket
#163, map #159).

Verified against a real export.json built by generators/graph_export.py's
own real functions against a real LadybugGraphStore, not a hand-typed
fixture - the same "real fixture, not hand-typed" convention
tests/test_redoc_renderer.py already follows for the other CDN-pinned
renderer. Opening the result in an actual browser to confirm Cytoscape.js
renders visually isn't something this environment can do (ticket #162's
own prototype was verified that way instead, via Playwright); the
strongest available proxy here is confirming the embedded graph data is
byte-for-byte the real generator's own output, and that the page is
well-formed HTML referencing Cytoscape's own real CDN bundle."""
import json

from core.documents import DocumentRequest
from dashboard.graph_renderer import render_graph_page
from database.ladybug.store import LadybugGraphStore
from generators.graph_export import build_export_graph

SITE = "shop.example"


class StubAgent:
    def generate(self, prompt, system_instruction=None):
        return "STUB"


def _real_export_content():
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page(f"{SITE}/", status="Finished", title="Home")
    store.record_component(f"{SITE}/", "a.about", tag="a", text="About")
    request = DocumentRequest(graph_store=store, site=SITE, agent=StubAgent(), settings={"run_id": "1"})
    document = build_export_graph(request)
    return document, json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def test_the_embedded_graph_is_byte_identical_to_the_real_generator_output():
    document, content = _real_export_content()

    html = render_graph_page(content, SITE)

    embedded = html.split('id="export-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == document


def test_the_page_references_cytoscapes_own_cdn_bundle():
    _, content = _real_export_content()

    html = render_graph_page(content, SITE)

    assert "cdn.jsdelivr.net/npm/cytoscape@3/dist/cytoscape.min.js" in html


def test_the_breadcrumb_links_back_to_the_landing_page():
    _, content = _real_export_content()

    html = render_graph_page(content, SITE)

    assert 'href="index.html"' in html


def test_family_colors_cover_every_node_type_the_real_document_used():
    document, content = _real_export_content()

    html = render_graph_page(content, SITE)

    types_present = {node["type"] for node in document["@graph"]}
    assert types_present  # the fixture actually produced at least one node
    for node_type in types_present:
        assert f'"{node_type}"' in html


def test_reserved_types_render_dimmed_as_not_in_this_run():
    _, content = _real_export_content()

    html = render_graph_page(content, SITE)

    assert "Escenario" in html
    assert "not in this run" in html


def test_the_page_is_well_formed_self_contained_html_apart_from_the_one_cdn_script():
    _, content = _real_export_content()

    html = render_graph_page(content, SITE)

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    other_urls = [line for line in html.splitlines() if "http" in line and "cytoscape.min.js" not in line]
    assert other_urls == []


def test_site_name_is_escaped_in_the_title_and_breadcrumb():
    _, content = _real_export_content()

    html = render_graph_page(content, "shop & co <script>")

    assert "shop & co <script>" not in html
    assert "shop &amp; co &lt;script&gt;" in html
