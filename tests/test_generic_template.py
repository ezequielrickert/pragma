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


def _markdown_document(name="prd", title="Digital Blueprint"):
    return ProducedDocument(
        name=name, title=title, purpose="Rendered Markdown.", path=f"/out/x_{name}_1.md",
        kind="view", checksum="a" * 64, filename=name, relative_link=f"x_{name}_1.md",
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


def test_a_md_view_document_renders_as_real_html_not_raw_syntax():
    """The gap ticket #144 exists for: raw '#'/'>'/'| --- |' syntax
    should never reach the page for a .md document."""
    html = render_generic_page(_markdown_document(), "# Heading\n\n| a | b |\n|---|---|\n| 1 | 2 |")

    assert "<h1>Heading</h1>" in html
    assert "<table>" in html and "<th>a</th>" in html
    assert "| --- |" not in html
    assert "# Heading" not in html


def test_a_non_md_view_document_still_gets_the_pre_fallback():
    """kind alone isn't the signal - llms.txt is kind='view' too but
    isn't Markdown (master_document.py)."""
    document = ProducedDocument(
        name="master", title="Start Here", purpose="The index.", path="/out/x_llms_1.txt",
        kind="view", checksum="a" * 64, filename="llms", relative_link="x_llms_1.txt",
    )

    html = render_generic_page(document, "# Not actually Markdown here")

    assert "<pre>" in html
    assert "<h1>Not actually Markdown here</h1>" not in html


def test_a_script_tag_smuggled_through_scraped_content_never_executes():
    """Every document here traces back to text scraped off a crawled
    site - Python-Markdown passes raw HTML through by design, so this
    has to be sanitized after conversion, not just escaped like the
    <pre> fallback does. The <script> tag itself is what has to be gone
    (nothing left for a browser to execute) - bleach.clean(strip=True)
    unwraps a disallowed tag rather than deleting its text content, so
    the source text can still appear as inert prose, same as it would
    for any other stripped tag."""
    html = render_generic_page(_markdown_document(), "Some text.\n\n<script>alert(document.cookie)</script>")

    assert "<script>" not in html and "</script>" not in html


def test_a_javascript_scheme_link_loses_its_href_but_a_real_link_keeps_it():
    """A distinct attack surface from the <script> tag case above - an
    attribute value, not an element. bleach's default protocol allowlist
    (http/https/mailto) drops javascript: from href while leaving a real
    link untouched."""
    html = render_generic_page(_markdown_document(), "[click me](javascript:alert(1))")
    assert "javascript:" not in html

    safe_html = render_generic_page(_markdown_document(), "[real link](https://example.com)")
    assert 'href="https://example.com"' in safe_html


def test_the_page_is_self_contained_static_html():
    """No external script/stylesheet requests - ADR-0016 point 1's own
    no-server, no-build-step constraint."""
    html = render_generic_page(_document("source"), "content")

    assert "<!doctype html>" in html
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html
