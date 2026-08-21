"""Unit tests for dashboard/shell.py - the Phase C landing page, per-
concern pages, and per-document renders (ADR-0016 point 4, ticket #125)."""
import json

from core.documents import ProducedDocument
from dashboard.shell import KpiContext, _document_slug, _source_json, build_dashboard

SITE = "shop.example"


def _document(name, kind, filename=None, title=None, path="/out/x.json"):
    return ProducedDocument(
        name=name, title=title or name.title(), purpose=f"{name} purpose.", path=path,
        kind=kind, checksum="a" * 64, filename=filename or name, relative_link="x.json",
    )


def _kpi():
    return KpiContext(pages_finished=3, pages_total=5, components_explored=2, components_total=4)


# --- _source_json ---

def test_finds_the_named_sources_own_json_content():
    documents = [(_document("coverage", "source"), '{"routes": {"visited": 3}}')]

    assert _source_json(documents, "coverage") == {"routes": {"visited": 3}}


def test_a_view_output_of_the_same_name_is_not_mistaken_for_the_source():
    documents = [(_document("coverage", "view"), "# Coverage\n")]

    assert _source_json(documents, "coverage") is None


def test_a_name_this_run_never_produced_is_none_not_an_error():
    assert _source_json([], "confidence-summary") is None


def test_malformed_json_is_none_not_a_crash():
    documents = [(_document("coverage", "source"), "not json")]

    assert _source_json(documents, "coverage") is None


# --- _document_slug ---

def test_a_source_view_pair_sharing_one_filename_gets_distinct_slugs():
    """filename alone collides for coverage.json/coverage.md - kind
    disambiguates."""
    source = _document("coverage", "source", filename="coverage")
    view = _document("coverage", "view", filename="coverage")

    assert _document_slug(source) != _document_slug(view)


# --- build_dashboard ---

def test_the_landing_page_shows_real_kpi_numbers():
    documents = [
        (_document("coverage", "source"), json.dumps({"endpoints": {"observed": 7}})),
    ]

    pages = build_dashboard(documents, _kpi(), SITE)

    landing = pages["dashboard/index.html"]
    assert "3 / 5" in landing  # pages
    assert "2 / 4" in landing  # components
    assert ">7<" in landing  # endpoints, from coverage.json


def test_a_kpi_with_no_source_document_reads_not_available_not_a_fabricated_number():
    pages = build_dashboard([], _kpi(), SITE)

    assert "not available this run" in pages["dashboard/index.html"]


def test_requirement_confidence_reads_from_confidence_summary_json():
    confidence = {"sources": {"prd": {"by_confidence": {"observed": 2, "inferred": 1, "assumed": 0}}}}
    documents = [(_document("confidence-summary", "source"), json.dumps(confidence))]

    pages = build_dashboard(documents, _kpi(), SITE)

    assert "observed 2" in pages["dashboard/index.html"]


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


def test_no_documents_at_all_produces_a_landing_page_with_an_empty_grid_not_an_error():
    pages = build_dashboard([], _kpi(), SITE)

    assert 'class="grid"></div>' in pages["dashboard/index.html"]
