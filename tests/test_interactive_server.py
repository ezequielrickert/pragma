"""Unit tests for interactive/server.py - Flask's own test client,
never a real bound socket. ServerThread's real make_server()/thread
lifecycle is exercised separately, not through these route tests."""
import time
from unittest.mock import Mock

from interactive.customization import DocumentRef, SiteOutput, save_customized
from interactive.server import create_app

SITE = "example.com"


def _write_original(tmp_path, filename, extension, content):
    (tmp_path / f"{SITE}_{filename}_20260101T000000Z.{extension}").write_text(content, encoding="utf-8")


def test_index_lists_every_available_document(tmp_path):
    _write_original(tmp_path, "tokens", "json", "{}")
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = create_app(str(tmp_path), SITE).test_client()

    html = client.get("/").get_data(as_text=True)

    assert "tokens.json" in html
    assert "gherkin.feature" in html


def test_get_document_shows_the_effective_content_in_a_textarea(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = create_app(str(tmp_path), SITE).test_client()

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

    assert "Feature: original" in html
    assert "<textarea" in html


def test_get_a_document_that_was_never_produced_is_404(tmp_path):
    client = create_app(str(tmp_path), SITE).test_client()

    response = client.get("/document/tokens.json")

    assert response.status_code == 404


def test_post_valid_content_saves_and_redirects(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = create_app(str(tmp_path), SITE).test_client()

    response = client.post("/document/gherkin.feature", data={"content": "Feature: edited\n"})

    assert response.status_code == 302
    saved = (tmp_path / "customized" / f"{SITE}_gherkin.feature").read_text(encoding="utf-8")
    assert saved == "Feature: edited\n"


def test_post_content_that_breaks_the_schema_shows_the_real_error_and_does_not_save(tmp_path):
    _write_original(tmp_path, "coverage", "json", "{}")
    client = create_app(str(tmp_path), SITE).test_client()

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
    client = create_app(str(tmp_path), SITE).test_client()

    html = client.get("/document/gherkin.feature").get_data(as_text=True)

    assert "Feature: already customized" in html
    assert "Feature: original" not in html


def test_finalizar_triggers_shutdown_on_a_background_thread(tmp_path):
    app = create_app(str(tmp_path), SITE)
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
