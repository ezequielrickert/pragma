"""Unit tests for dashboard/kpi_section.py - the landing page's own
crawl-wide metrics row (ADR-0016 point 4), split out of
dashboard/shell.py (ticket #176, map #172)."""
from core.documents import ProducedDocument
from dashboard.kpi_section import KpiContext, kpi_section, source_content, source_json

SITE = "shop.example"


def _document(name, kind, filename=None, title=None, path="/out/x.json"):
    return ProducedDocument(
        name=name, title=title or name.title(), purpose=f"{name} purpose.", path=path,
        kind=kind, checksum="a" * 64, filename=filename or name, relative_link="x.json",
    )


def _kpi():
    return KpiContext(pages_finished=3, pages_total=5, components_explored=2, components_total=4)


# --- source_json ---

def test_finds_the_named_sources_own_json_content():
    documents = [(_document("coverage", "source"), '{"routes": {"visited": 3}}')]

    assert source_json(documents, "coverage") == {"routes": {"visited": 3}}


def test_a_view_output_of_the_same_name_is_not_mistaken_for_the_source():
    documents = [(_document("coverage", "view"), "# Coverage\n")]

    assert source_json(documents, "coverage") is None


def test_a_name_this_run_never_produced_is_none_not_an_error():
    assert source_json([], "confidence-summary") is None


def test_malformed_json_is_none_not_a_crash():
    documents = [(_document("coverage", "source"), "not json")]

    assert source_json(documents, "coverage") is None


# --- source_content ---

def test_source_content_returns_the_raw_text_unparsed():
    documents = [(_document("export", "source"), '{"@graph": []}')]

    assert source_content(documents, "export") == '{"@graph": []}'


def test_source_content_is_none_for_a_name_this_run_never_produced():
    assert source_content([], "export") is None


# --- kpi_section ---

def test_a_kpi_with_no_source_document_reads_not_available_not_a_fabricated_number():
    html = kpi_section([], _kpi(), graph_available=False)

    assert "not available this run" in html


def test_a_kpi_with_a_real_denominator_gets_a_real_percent_ring():
    html = kpi_section([], _kpi(), graph_available=False)  # 3/5 pages = 60%

    assert "conic-gradient(var(--accent) 60%" in html


def test_a_kpi_with_no_natural_denominator_gets_an_empty_ring_not_a_fabricated_percent():
    documents = [(_document("coverage", "source"), '{"endpoints": {"observed": 7}}')]

    html = kpi_section(documents, _kpi(), graph_available=False)

    assert 'style="background:var(--panel-2)"></div><div><div class="value">7</div>' in html


def test_confidence_tile_leads_with_the_real_total_not_the_split():
    confidence = '{"sources": {"prd": {"total": 3, "by_confidence": {"observed": 2, "inferred": 1, "assumed": 0}}}}'
    documents = [(_document("confidence-summary", "source"), confidence)]

    html = kpi_section(documents, _kpi(), graph_available=False)

    assert '<div class="value">3</div>' in html
    assert "observed 2" in html  # the split, now the tile's own secondary label


def test_usability_and_accessibility_finding_totals_read_from_confidence_summary():
    confidence = '{"sources": {"usability": {"total": 5}, "accessibility": {"total": 8}}}'
    documents = [(_document("confidence-summary", "source"), confidence)]

    html = kpi_section(documents, _kpi(), graph_available=False)

    assert '<div class="value">5</div>' in html
    assert '<div class="value">8</div>' in html


def test_tiles_link_through_to_the_graph_pre_filtered_to_their_own_family_when_available():
    html = kpi_section([], _kpi(), graph_available=True)

    assert 'href="graph.html?family=Pantalla"' in html
    assert 'href="graph.html?family=Componente"' in html
    assert 'href="graph.html?family=Requisito"' in html
    assert 'href="graph.html?family=Endpoint"' in html


def test_tiles_dont_link_when_the_graph_page_isnt_available_this_run():
    html = kpi_section([], _kpi(), graph_available=False)

    assert "graph.html?family=" not in html


def test_usability_and_accessibility_tiles_never_link_no_populated_graph_family_for_them():
    """Hallazgo stays reserved (ADR-0002) - never populated in a real
    export.json - so these two tiles show their number with no link,
    never one pointing at a family that would always render empty."""
    confidence = '{"sources": {"usability": {"total": 5}, "accessibility": {"total": 8}}}'
    documents = [(_document("confidence-summary", "source"), confidence)]

    html = kpi_section(documents, _kpi(), graph_available=True)

    assert '<div class="kpi">' in html  # at least one non-linkable tile rendered as a plain div
