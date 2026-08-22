"""Unit tests for interactive/server.py - Flask's own test client,
never a real bound socket. ServerThread's real make_server()/thread
lifecycle is exercised separately, not through these route tests."""
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

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

    assert "Feature: original" in html
    assert "<textarea" in html


def test_get_a_document_that_was_never_produced_is_404(tmp_path):
    client = _app(tmp_path).test_client()

    response = client.get("/document/tokens.json")

    assert response.status_code == 404


def test_post_valid_content_saves_and_redirects(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = _app(tmp_path).test_client()

    response = client.post("/document/gherkin.feature", data={"content": "Feature: edited\n"})

    assert response.status_code == 302
    saved = (tmp_path / "customized" / f"{SITE}_gherkin.feature").read_text(encoding="utf-8")
    assert saved == "Feature: edited\n"


def test_post_content_that_breaks_the_schema_shows_the_real_error_and_does_not_save(tmp_path):
    _write_original(tmp_path, "coverage", "json", "{}")
    client = _app(tmp_path).test_client()

    response = client.post("/document/coverage.json", data={"content": "{}"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "class=\"error\"" in html
    assert not (tmp_path / "customized" / f"{SITE}_coverage.json").exists()


def test_editing_a_document_that_is_already_customized_edits_the_customized_copy(tmp_path):
    """The effective-content rule (ADR-0031), exercised through a real
    request rather than just customization.py directly."""
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    save_customized(SiteOutput(str(tmp_path), SITE), DocumentRef("gherkin", "feature"), "Feature: already customized\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

    assert "Feature: already customized" in html
    assert "Feature: original" not in html


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

    html = client.get("/document/tokens.json").get_data(as_text=True)

    assert 'type="color"' in html
    assert 'value="#2d7737"' in html
    assert "core.color.surface-1" in html


def test_a_non_tokens_page_shows_no_color_form(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = _app(tmp_path).test_client()

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

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

    html = client.get("/document/tokens.json").get_data(as_text=True)

    assert "<textarea" in html
    assert 'type="color"' in html
