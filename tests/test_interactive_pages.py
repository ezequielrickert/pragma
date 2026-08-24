"""Unit tests for interactive/pages.py's own rendering logic - direct,
not routed through interactive/server.py's Flask test client (ticket
#155's diff/error-gutter addition). `document_page` still needs a real
app/request context (it calls `url_for("index")`), so every call below
runs inside one - a bare `Flask(__name__)` won't do, since "index" is
only registered on the app `create_app` builds."""
from unittest.mock import Mock

from interactive.customization import DocumentRef
from interactive.pages import DocumentEditState, DocumentViewState, ValidationFailure, _approximate_line_for_path, document_page
from interactive.server import create_app

REF = DocumentRef("gherkin", "feature")


def _document_page(ref, state):
    app = create_app("unused", "example.com", Mock())
    with app.test_request_context():
        return document_page(ref, state)


def test_approximate_line_for_path_finds_the_unique_matching_line():
    content = 'line one\n{"surface-1": {"$value": "#2d7737"}}\nline three\n'

    line = _approximate_line_for_path(content, ["core", "color", "surface-1"])

    assert line == 2


def test_approximate_line_for_path_is_none_when_nothing_matches():
    content = "no keys here at all\n"

    assert _approximate_line_for_path(content, ["surface-1"]) is None


def test_approximate_line_for_path_is_none_when_the_key_appears_on_two_lines():
    """A wrong guess is worse than an honest 'can't point at a line' -
    ambiguous matches decline rather than picking one arbitrarily."""
    content = '"surface-1" here\n"surface-1" again\n'

    assert _approximate_line_for_path(content, ["surface-1"]) is None


def test_document_page_shows_both_original_and_current_content():
    state = DocumentEditState(content="Feature: edited\n", original="Feature: original\n", failure=None)

    html = _document_page(REF, state)

    assert 'id="orig-pane"' in html and "Feature: original" in html
    assert 'id="edit-content"' in html and "Feature: edited" in html


def test_document_page_with_no_failure_paints_no_error_line():
    state = DocumentEditState(content="x", original="x", failure=None)

    html = _document_page(REF, state)

    assert "paintGutters(null)" in html
    assert 'class="error"' not in html


def test_document_page_with_a_failure_shows_the_message_and_the_approximate_line():
    content = '{"core": {"color": {"surface-1": {"$type": "color"}}}}\n'
    failure = ValidationFailure(message="'$value' is a required property", path=["core", "color", "surface-1"])
    state = DocumentEditState(content=content, original=content, failure=failure)

    html = _document_page(REF, state)

    assert "$value" in html and "is a required property" in html  # escape() turns ' into &#x27;
    assert "paintGutters(1)" in html


def test_document_view_page_renders_based_on_renderer():
    from interactive.pages import document_view_page
    app = create_app("unused", "example.com", Mock())
    with app.test_request_context():
        # Markdown
        html_md = document_view_page(DocumentRef("prd", "md"), DocumentViewState("# Hello\n- world"), "generic")
        assert "<h1>Hello</h1>" in html_md
        assert "<li>world</li>" in html_md
        assert 'class="edit-link"' in html_md

        # OpenAPI (redoc)
        html_openapi = document_view_page(DocumentRef("openapi", "yaml"), DocumentViewState("openapi: 3.0.0\n"), "redoc")
        assert "redoc-container" in html_openapi
        assert 'class="edit-link"' in html_openapi

        # Generic pre-formatted
        html_feature = document_view_page(DocumentRef("gherkin", "feature"), DocumentViewState("Feature: raw"), "generic")
        assert "<pre>Feature: raw</pre>" in html_feature
        assert 'class="edit-link"' in html_openapi


def test_document_view_page_renders_diff_summary():
    from interactive.pages import document_view_page
    app = create_app("unused", "example.com", Mock())
    with app.test_request_context():
        # Markdown diff
        html_md = document_view_page(
            DocumentRef("prd", "md"),
            DocumentViewState(content="# Current\n", original="# Original\n"),
            "generic"
        )
        assert 'class="diff-panes"' in html_md
        assert "<h3>Original</h3>" in html_md
        assert "<h3>Current</h3>" in html_md
        assert "<h1>Original</h1>" in html_md
        assert "<h1>Current</h1>" in html_md

        # Redoc diff
        html_openapi = document_view_page(
            DocumentRef("openapi", "yaml"),
            DocumentViewState(
                content="openapi: 3.0.0\ninfo:\n  title: Current API\n",
                original="openapi: 3.0.0\ninfo:\n  title: Original API\n"
            ),
            "redoc"
        )
        assert 'class="diff-panes"' in html_openapi
        assert "redoc-container-orig" in html_openapi
        assert "redoc-container-curr" in html_openapi



