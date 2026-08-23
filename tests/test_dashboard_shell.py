"""Unit tests for dashboard/shell.py - the Phase C landing page, per-
concern pages, and per-document renders (ADR-0016 point 4, ticket #125).
`source_content`/`source_json`/the KPI row itself have their own tests in
tests/test_kpi_section.py, alongside dashboard/kpi_section.py."""
import json

from core.documents import ProducedDocument
from dashboard.kpi_section import KpiContext
from dashboard.shell import _document_slug, build_dashboard

SITE = "shop.example"


def _document(name, kind, filename=None, title=None, path="/out/x.json"):
    return ProducedDocument(
        name=name, title=title or name.title(), purpose=f"{name} purpose.", path=path,
        kind=kind, checksum="a" * 64, filename=filename or name, relative_link="x.json",
    )


def _kpi():
    return KpiContext(pages_finished=3, pages_total=5, components_explored=2, components_total=4)


# --- _document_slug ---

def test_a_source_view_pair_sharing_one_filename_gets_distinct_slugs():
    """filename alone collides for coverage.json/coverage.md - kind
    disambiguates."""
    source = _document("coverage", "source", filename="coverage")
    view = _document("coverage", "view", filename="coverage")

    assert _document_slug(source) != _document_slug(view)


# --- build_dashboard ---

def test_the_landing_page_wires_kpi_context_and_documents_through_to_the_kpi_section():
    """The KPI section's own real behavior (rings, totals, click-through)
    has its own tests in tests/test_kpi_section.py - this only confirms
    build_dashboard actually threads its two real inputs (kpi_context,
    documents) through to it, not a second copy of that behavior."""
    documents = [(_document("coverage", "source"), json.dumps({"endpoints": {"observed": 7}}))]

    pages = build_dashboard(documents, _kpi(), SITE)

    landing = pages["dashboard/index.html"]
    assert "3 / 5" in landing  # pages, from the KpiContext argument
    assert ">7<" in landing  # endpoints, from coverage.json in the documents argument


def test_kpi_tiles_link_through_only_when_the_graph_page_is_actually_available():
    """graph_available is build_dashboard's own computed fact (whether
    export.json was produced this run) - kpi_section only renders what
    it's told, so this is what actually exercises that wiring."""
    with_export = build_dashboard(
        [(_document("export", "source", filename="export"), '{"@graph": []}')], _kpi(), SITE
    )
    without_export = build_dashboard([], _kpi(), SITE)

    assert 'href="graph.html?family=Pantalla"' in with_export["dashboard/index.html"]
    assert "graph.html?family=" not in without_export["dashboard/index.html"]


def test_one_card_per_concern_on_the_landing_page():
    documents = [
        (_document("prd", "source", filename="requirements"), "{}"),
        (_document("prd", "view", filename="prd"), "# PRD"),
        (_document("openapi", "source", filename="openapi"), "openapi: 3.1.0"),
    ]

    pages = build_dashboard(documents, _kpi(), SITE)

    landing = pages["dashboard/index.html"]
    assert 'href="concern/prd.html"' in landing
    assert 'href="concern/openapi.html"' in landing
    assert "dashboard/concern/prd.html" in pages
    assert "dashboard/concern/openapi.html" in pages


def test_master_is_excluded_from_the_concern_grid():
    documents = [(_document("master", "view", filename="master"), "# Start Here")]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert "dashboard/concern/master.html" not in pages
    assert 'href="concern/master.html"' not in pages["dashboard/index.html"]


def test_master_is_excluded_from_per_document_renders_too():
    documents = [(_document("master", "source", filename="manifest"), "{}")]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert not any(key.startswith("dashboard/document/manifest") for key in pages)


def test_a_concern_page_lists_every_one_of_its_own_outputs():
    documents = [
        (_document("prd", "source", filename="requirements"), "{}"),
        (_document("prd", "view", filename="prd"), "# PRD"),
    ]

    pages = build_dashboard(documents, _kpi(), SITE)

    concern_page = pages["dashboard/concern/prd.html"]
    assert "requirements" in concern_page
    assert "prd" in concern_page
    assert 'href="../index.html"' in concern_page  # breadcrumb back to the landing page


def test_every_produced_document_gets_its_own_rendered_page():
    documents = [(_document("coverage", "source", filename="coverage"), '{"a": 1}')]

    pages = build_dashboard(documents, _kpi(), SITE)

    slug = _document_slug(documents[0][0])
    assert f"dashboard/document/{slug}.html" in pages
    assert '{&quot;a&quot;: 1}' in pages[f"dashboard/document/{slug}.html"]


def test_no_documents_at_all_produces_a_landing_page_with_no_concern_cards_not_an_error():
    """The grid isn't literally empty - the Graph card always renders,
    just unavailable with no export.json to back it (see the Graph-card
    tests below)."""
    pages = build_dashboard([], _kpi(), SITE)

    assert 'href="concern/' not in pages["dashboard/index.html"]


# --- Graph card (ticket #163, map #159) ---

def test_the_graph_card_links_to_a_real_graph_page_when_export_json_was_produced():
    documents = [(_document("export", "source", filename="export"), '{"@graph": []}')]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert 'href="graph.html"' in pages["dashboard/index.html"]
    assert "dashboard/graph.html" in pages


def test_the_graph_card_reads_not_available_when_export_json_was_never_produced():
    pages = build_dashboard([], _kpi(), SITE)

    landing = pages["dashboard/index.html"]
    assert "dashboard/graph.html" not in pages
    assert 'href="graph.html"' not in landing
    assert "Graph" in landing and "not available this run" in landing


def test_the_graph_page_embeds_the_real_export_json_content():
    export_content = '{"@graph": [{"id": "example.com", "type": "Pantalla"}]}'
    documents = [(_document("export", "source", filename="export"), export_content)]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert export_content in pages["dashboard/graph.html"]
    assert 'href="index.html"' in pages["dashboard/graph.html"]  # breadcrumb back to the landing page


def test_the_export_concern_still_gets_its_own_ordinary_concern_page_too():
    """The Graph card is additional, not a replacement - export.json's
    usual concern/document flow (the raw-JSON view) stays reachable."""
    documents = [(_document("export", "source", filename="export"), '{"@graph": []}')]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert 'href="concern/export.html"' in pages["dashboard/index.html"]
    assert "dashboard/concern/export.html" in pages
