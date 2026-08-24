"""Unit tests for interactive/server.py - Flask's own test client,
never a real bound socket. ServerThread's real make_server()/thread
lifecycle is exercised separately, not through these route tests."""
import json
import time
from unittest.mock import Mock

from interactive.customization import DocumentRef, SiteOutput, save_customized
from interactive.server import create_app

SITE = "example.com"


class _StubAgent:
    """A minimal Agent double - `reply`/`error` are set per test to
    control what the chat route sees back from "the model"."""

    def __init__(self, reply="a reply", error=None):
        self.reply = reply
        self.error = error
        self.seen_messages = None
        self.seen_system_instruction = None

    def generate(self, prompt, system_instruction=None):
        return self.reply

    def converse(self, messages, system_instruction=None):
        # A snapshot, not the same list reference - the route appends
        # the assistant's own reply onto `messages` right after this
        # call returns, which would otherwise silently mutate whatever
        # a test captured here too.
        self.seen_messages = list(messages)
        self.seen_system_instruction = system_instruction
        if self.error:
            raise self.error
        return self.reply


def _app(tmp_path, agent=None):
    return create_app(str(tmp_path), SITE, agent or _StubAgent())


def _write_original(tmp_path, filename, extension, content):
    (tmp_path / f"{SITE}_{filename}_20260101T000000Z.{extension}").write_text(content, encoding="utf-8")


def test_index_lists_every_available_document(tmp_path):
    _write_original(tmp_path, "tokens", "json", "{}")
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = _app(tmp_path).test_client()

    html = client.get("/").get_data(as_text=True)

    assert "tokens.json" in html
    assert "gherkin.feature" in html


def test_get_document_shows_the_effective_content_in_a_textarea(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature/edit").get_data(as_text=True)

    assert "Feature: original" in html
    assert "<textarea" in html


def test_get_document_wires_the_real_original_alongside_the_customized_current(tmp_path):
    """A unit test of pages.py::document_page alone can't catch this -
    it would happily accept the same string for both `original` and
    `content`. This exercises the real route, where a bug forgetting
    to fetch original_content (or passing `content` for both) would
    make the diff panes identical without failing anything else."""
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    save_customized(SiteOutput(str(tmp_path), SITE), DocumentRef("gherkin", "feature"), "Feature: edited\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature/edit").get_data(as_text=True)
    original_pane = html.split('id="orig-pane"')[1].split("</pre>")[0]
    editable_content = html.split('id="edit-content"')[1].split("</textarea>")[0]

    assert "Feature: original" in original_pane
    assert "Feature: edited" in editable_content
    assert "Feature: original" not in editable_content


def test_get_a_document_that_was_never_produced_is_404(tmp_path):
    client = _app(tmp_path).test_client()

    response = client.get("/document/tokens.json")

    assert response.status_code == 404


def test_post_valid_content_saves_and_redirects(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = _app(tmp_path).test_client()

    response = client.post("/document/gherkin.feature/edit", data={"content": "Feature: edited\n"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/document/gherkin.feature"
    saved = (tmp_path / "customized" / f"{SITE}_gherkin.feature").read_text(encoding="utf-8")
    assert saved == "Feature: edited\n"


def test_post_content_that_breaks_the_schema_shows_the_real_error_and_does_not_save(tmp_path):
    _write_original(tmp_path, "coverage", "json", "{}")
    client = _app(tmp_path).test_client()

    response = client.post("/document/coverage.json/edit", data={"content": "{}"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "class=\"error\"" in html
    assert not (tmp_path / "customized" / f"{SITE}_coverage.json").exists()


def test_editing_a_document_that_is_already_customized_edits_the_customized_copy(tmp_path):
    """The effective-content rule (ADR-0031), exercised through a real
    request rather than just customization.py directly. The original
    is legitimately shown too now (ticket #155's own diff pane) - what
    this test actually guards is that the *editable* textarea (what a
    save submits) holds the customized content, never the original."""
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    save_customized(SiteOutput(str(tmp_path), SITE), DocumentRef("gherkin", "feature"), "Feature: already customized\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature/edit").get_data(as_text=True)
    editable_content = html.split('id="edit-content"')[1].split("</textarea>")[0]

    assert "Feature: already customized" in editable_content
    assert "Feature: original" not in editable_content


def test_finalizar_triggers_shutdown_on_a_background_thread(tmp_path):
    app = _app(tmp_path)
    fake_server_thread = Mock()
    app.config["SERVER_THREAD"] = fake_server_thread
    client = app.test_client()

    response = client.post("/finalizar")

    assert response.status_code == 200
    # shutdown() runs on a spawned thread (must not be the request's own
    # thread - the stdlib socketserver requirement) - poll briefly
    # rather than assume it already ran by the time the response returns.
    deadline = time.monotonic() + 1.0
    while not fake_server_thread.shutdown.called and time.monotonic() < deadline:
        time.sleep(0.01)
    fake_server_thread.shutdown.assert_called_once()


def test_chat_sends_the_message_and_renders_the_reply(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    agent = _StubAgent(reply="Looks like a safe change.")
    client = _app(tmp_path, agent).test_client()

    response = client.post("/document/gherkin.feature/chat", data={"message": "Is this safe to remove?"})
    html = response.get_data(as_text=True)

    assert "Is this safe to remove?" in html
    assert "Looks like a safe change." in html
    assert agent.seen_messages == [{"role": "user", "content": "Is this safe to remove?"}]


def test_chat_grounds_tokens_json_with_a_real_usa_token_citer(tmp_path):
    """The system_instruction actually carries a real grounding fact,
    not just a static template - exercised end to end through the
    route, not interactive/grounding.py directly."""
    _write_original(tmp_path, "tokens", "json", '{"core": {"color": {"surface-1": '
                    '{"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    _write_original(tmp_path, "export", "json", '{"@graph": ['
                    '{"id": "core.color.surface-1", "type": "Token"}, '
                    '{"id": "example.com/|button.buy", "type": "Componente", '
                    '"usa_token": ["core.color.surface-1"]}]}')
    agent = _StubAgent()
    client = _app(tmp_path, agent).test_client()

    client.post("/document/tokens.json/chat", data={"message": "What uses this?"})

    assert "core.color.surface-1" in agent.seen_system_instruction
    assert "example.com/|button.buy" in agent.seen_system_instruction


def test_chat_history_accumulates_across_turns(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    agent = _StubAgent()
    client = _app(tmp_path, agent).test_client()

    client.post("/document/gherkin.feature/chat", data={"message": "first"})
    client.post("/document/gherkin.feature/chat", data={"message": "second"})

    assert [m["content"] for m in agent.seen_messages] == ["first", "a reply", "second"]


def test_chat_history_is_scoped_per_document(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    _write_original(tmp_path, "tokens", "json", "{}")
    agent = _StubAgent()
    client = _app(tmp_path, agent).test_client()

    client.post("/document/gherkin.feature/chat", data={"message": "about gherkin"})
    client.post("/document/tokens.json/chat", data={"message": "about tokens"})

    assert [m["content"] for m in agent.seen_messages] == ["about tokens"]


def test_a_model_failure_shows_a_real_error_and_does_not_keep_the_unanswered_turn(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    agent = _StubAgent(error=RuntimeError("Local API request failed: connection refused"))
    client = _app(tmp_path, agent).test_client()

    response = client.post("/document/gherkin.feature/chat", data={"message": "hello"})
    html = response.get_data(as_text=True)

    assert "connection refused" in html
    # A retried message must not see a stale, already-failed turn ahead of it.
    client.post("/document/gherkin.feature/chat", data={"message": "hello again"})
    assert [m["content"] for m in agent.seen_messages] == ["hello again"]


def test_tokens_page_shows_a_color_picker_per_core_color_token(tmp_path):
    _write_original(tmp_path, "tokens", "json",
                     '{"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    client = _app(tmp_path).test_client()

    html = client.get("/document/tokens.json/edit").get_data(as_text=True)

    assert 'type="color"' in html
    assert 'value="#2d7737"' in html
    assert "core.color.surface-1" in html


def test_a_non_tokens_page_shows_no_color_form(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature/edit").get_data(as_text=True)

    assert 'class="color-tokens"' not in html


def test_saving_colors_patches_the_customized_tokens_json_and_redirects(tmp_path):
    _write_original(tmp_path, "tokens", "json",
                     '{"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    client = _app(tmp_path).test_client()

    response = client.post("/document/tokens.json/colors", data={"token:core.color.surface-1": "#0000ff"})

    assert response.status_code == 302
    saved = (tmp_path / "customized" / f"{SITE}_tokens.json").read_text(encoding="utf-8")
    assert '"$value": "#0000ff"' in saved


def test_the_raw_text_editor_still_works_on_the_tokens_page_alongside_the_color_form(tmp_path):
    """Coexistence, not replacement - map #146's own decision for Phase 2."""
    _write_original(tmp_path, "tokens", "json",
                     '{"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    client = _app(tmp_path).test_client()

    html = client.get("/document/tokens.json/edit").get_data(as_text=True)

    assert "<textarea" in html
    assert 'type="color"' in html


_REQUIREMENT = {
    "id": "REQ-a4f9000001", "ears_pattern": "event_driven", "syntax_text": "WHEN x, THE SYSTEM SHALL y",
    "confidence": "observed", "derived_from": [], "coverage_ref": {"run_id": "RUN-1"},
    "links": {"screens": [], "endpoints": [], "scenarios": [], "data_entities": [], "depends_on": []},
    "hitl_status": "unreviewed", "open_questions": [],
}


def test_the_requirements_page_shows_the_generic_review_form(tmp_path):
    _write_original(tmp_path, "requirements", "json", json.dumps({"requirements": [_REQUIREMENT]}))
    client = _app(tmp_path).test_client()

    html = client.get("/document/requirements.json/edit").get_data(as_text=True)

    assert 'class="generic-form"' in html
    assert "REQ-a4f9000001" in html
    assert "<select" in html  # hitl_status, schema-driven, not hand-picked
    assert "<textarea" in html  # both the raw-text editor and open_questions use one


def test_saving_generic_form_fields_patches_the_customized_requirements_json(tmp_path):
    _write_original(tmp_path, "requirements", "json", json.dumps({"requirements": [_REQUIREMENT]}))
    client = _app(tmp_path).test_client()

    response = client.post("/document/requirements.json/fields", data={"entry:0:hitl_status": "approved"})

    assert response.status_code == 302
    saved = (tmp_path / "customized" / f"{SITE}_requirements.json").read_text(encoding="utf-8")
    assert '"hitl_status": "approved"' in saved
    assert '"id": "REQ-a4f9000001"' in saved  # untouched fields survive


def test_a_document_with_no_generic_form_spec_shows_no_generic_form_panel(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature/edit").get_data(as_text=True)

    assert 'class="generic-form"' not in html


def test_view_mode_renders_markdown_to_html_for_md_document(tmp_path):
    _write_original(tmp_path, "prd", "md", "# PRD Requirements\n- Must support read-only view.")
    client = _app(tmp_path).test_client()

    html = client.get("/document/prd.md").get_data(as_text=True)

    assert "PRD Requirements" in html
    assert "Must support read-only view." in html
    assert "<li>" in html
    assert 'class="edit-link"' in html
    assert "<textarea" not in html


def test_view_mode_renders_redoc_for_openapi(tmp_path):
    _write_original(tmp_path, "openapi", "yaml", "openapi: 3.0.0\ninfo:\n  title: Test API\n  version: 1.0\npaths: {}\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/openapi.yaml").get_data(as_text=True)

    assert "redoc-container" in html
    assert "Test API" in html
    assert 'class="edit-link"' in html
    assert "<textarea" not in html


def test_view_mode_renders_pre_escaped_for_generic_files(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n  Scenario: <escaped>\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

    assert "<pre>Feature: x\n  Scenario: &lt;escaped&gt;\n</pre>" in html
    assert 'class="edit-link"' in html
    assert "<textarea" not in html


def test_view_mode_shows_diff_summary_when_customized_exists(tmp_path):
    _write_original(tmp_path, "prd", "md", "# Original PRD\n")
    # Save a customized copy
    save_customized(SiteOutput(str(tmp_path), SITE), DocumentRef("prd", "md"), "# Customized PRD\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/prd.md").get_data(as_text=True)

    assert 'class="diff-panes"' in html
    assert "Original" in html
    assert "Current" in html
    assert "<h1>Original PRD</h1>" in html
    assert "<h1>Customized PRD</h1>" in html



def test_api_graph_route(tmp_path):
    client = _app(tmp_path).test_client()

    response = client.get("/api/graph")

    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert "@context" in data
    assert "@graph" in data


def test_serve_graph_explorer_pages_and_assets(tmp_path):
    client = _app(tmp_path).test_client()

    # Get /graph (should redirect to /index.html)
    resp = client.get("/graph")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/index.html"

    # Get /index.html
    resp = client.get("/index.html")
    assert resp.status_code == 200
    assert "Graph Explorer" in resp.get_data(as_text=True)

    # Get /lists.html
    resp = client.get("/lists.html")
    assert resp.status_code == 200
    assert "Graph Explorer" in resp.get_data(as_text=True)
