"""Unit tests for dashboard/generic_template.py - the shared fallback
renderer every document without a dedicated Phase B renderer uses
(ADR-0016 point 2, ticket #123). One fixture per DocumentKind (source,
view, rule-catalog, projection), matching the ticket's own "Done when"
criterion."""
from core.documents import ProducedDocument
from dashboard.generic_template import render_generic_page


def _document(kind, name="requirements", title="Requirements", purpose="Requirements in EARS syntax."):
    return ProducedDocument(
        name=name, title=title, purpose=purpose, path=f"/out/x_{name}_1.json",
        kind=kind, checksum="a" * 64, filename=name, relative_link=f"x_{name}_1.json",
    )


def test_a_source_document_renders_its_title_purpose_and_content():
    html = render_generic_page(_document("source"), '{"requirements": []}')

    assert "<h1>Requirements</h1>" in html
    assert "Requirements in EARS syntax." in html
    # Double quotes are HTML-escaped too (defends attribute-context
    # injection, not just tag-context) - the escaped form is what a
    # correct renderer must produce.
    assert "requirements&quot;: []" in html
    assert 'class="badge source"' in html


def test_a_view_document_gets_the_view_badge():
    document = _document("view", name="prd", title="Requirements (view)", purpose="Rendered Markdown.")

    html = render_generic_page(document, "# Requirements\n\nNo requirements found.")

    assert 'class="badge view"' in html
    assert "No requirements found." in html


def test_a_rule_catalog_gets_the_rule_catalog_badge():
    document = _document("rule-catalog", name="usability-rules", title="Usability Rule Catalog", purpose="ACT Rules.")

    html = render_generic_page(document, '{"rules": []}')

    assert 'class="badge rule-catalog"' in html


def test_a_projection_gets_the_projection_badge():
    document = _document("projection", name="usability.sarif", title="Usability (SARIF)", purpose="SARIF projection.")

    html = render_generic_page(document, '{"runs": []}')

    assert 'class="badge projection"' in html


def test_content_is_html_escaped_so_a_json_angle_bracket_never_breaks_the_page():
    html = render_generic_page(_document("source"), '{"note": "<script>alert(1)</script>"}')

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_title_itself_is_escaped_too():
    document = _document("source", title="A <b>Title</b>")

    html = render_generic_page(document, "content")

    assert "<b>Title</b>" not in html
    assert "&lt;b&gt;" in html


def test_the_breadcrumb_links_back_to_the_documents_own_concern_page():
    """A document page has no way back to its concern page otherwise -
    ticket #143's own gap, `dashboard/shell.py`'s concern page already
    has this for the landing page."""
    document = _document("source", name="catalog", title="Component Catalogue")

    html = render_generic_page(document, "content")

    assert '<a href="../concern/catalog.html">&larr; Component Catalogue</a>' in html


def test_the_page_is_self_contained_static_html():
    """No external script/stylesheet requests - ADR-0016 point 1's own
    no-server, no-build-step constraint."""
    html = render_generic_page(_document("source"), "content")

    assert "<!doctype html>" in html
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html
