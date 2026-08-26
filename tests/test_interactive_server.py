"""Unit tests for interactive/server.py REST API endpoints - Flask's own
test client, never a real bound socket.
"""
import json
import time
from unittest.mock import Mock

from interactive.customization import DocumentRef, SiteOutput, save_customized
from interactive.server import create_app
from core.interfaces import Agent

SITE = "example.com"


class _StubAgent(Agent):
    """A minimal Agent double - `reply`/`error` are set per test to
    control what the chat route sees back from "the model"."""

    def __init__(self, reply="a reply", error=None):
        self.reply = reply
        self.error = error
        self.seen_messages: list[dict[str, str]] | None = None
        self.seen_system_instruction: str | None = None

    def generate(self, prompt, system_instruction=None):
        return self.reply

    def converse(self, messages, system_instruction=None):
        self.seen_messages = list(messages)
        self.seen_system_instruction = system_instruction
        if self.error:
            raise self.error
        return self.reply


def _app(tmp_path, agent=None):
    return create_app(str(tmp_path), SITE, agent or _StubAgent(), db_dir=str(tmp_path))


def _write_original(tmp_path, filename, extension, content):
    (tmp_path / f"{SITE}_{filename}_20260101T000000Z.{extension}").write_text(content, encoding="utf-8")


def _write_original_in_run_dir(tmp_path, filename, extension, content, timestamp="20260101T000000Z"):
    """Write a file in the new per-run subdirectory layout: <out_dir>/<slug>_<ts>/<slug>_<name>_<ts>.<ext>."""
    run_dir = tmp_path / f"{SITE}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{SITE}_{filename}_{timestamp}.{extension}").write_text(content, encoding="utf-8")


def test_api_sites_returns_crawled_slugs(tmp_path):
    # Create fake lbdb files to simulate crawled sites
    (tmp_path / "example.com.lbdb").write_text("", encoding="utf-8")
    (tmp_path / "another.com.lbdb").write_text("", encoding="utf-8")
    client = _app(tmp_path).test_client()

    response = client.get("/api/sites")
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert data == ["another.com", "example.com"]


def test_api_documents_lists_every_available_document(tmp_path):
    _write_original(tmp_path, "tokens", "json", "{}")
    _write_original(tmp_path, "gherkin", "feature", "Feature: x\n")
    client = _app(tmp_path).test_client()

    response = client.get(f"/api/{SITE}/documents")
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))

    filenames = [d["filename"] + "." + d["extension"] for d in data]
    assert "tokens.json" in filenames
    assert "gherkin.feature" in filenames


def test_api_documents_lists_docs_from_per_run_subdirectory(tmp_path):
    _write_original_in_run_dir(tmp_path, "tokens", "json", "{}")
    _write_original_in_run_dir(tmp_path, "prd", "md", "# PRD\n")
    client = _app(tmp_path).test_client()

    response = client.get(f"/api/{SITE}/documents")
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))

    filenames = [d["filename"] + "." + d["extension"] for d in data]
    assert "tokens.json" in filenames
    assert "prd.md" in filenames


def test_api_document_detail_returns_content_and_original(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    save_customized(SiteOutput(str(tmp_path), SITE), DocumentRef("gherkin", "feature"), "Feature: edited\n")
    client = _app(tmp_path).test_client()

    response = client.get(f"/api/{SITE}/documents/gherkin.feature")
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))

    assert data["filename"] == "gherkin"
    assert data["extension"] == "feature"
    assert data["original"] == "Feature: original\n"
    assert data["content"] == "Feature: edited\n"
    assert data["customized"] is True
    assert data["renderer"] == "generic"


def test_api_document_detail_not_found_is_404(tmp_path):
    client = _app(tmp_path).test_client()
    response = client.get(f"/api/{SITE}/documents/tokens.json")
    assert response.status_code == 404


def test_api_save_document_commits_content(tmp_path):
    _write_original(tmp_path, "gherkin", "feature", "Feature: original\n")
    client = _app(tmp_path).test_client()

    response = client.post(
        f"/api/{SITE}/documents/gherkin.feature",
        json={"content": "Feature: edited\n"}
    )
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert data["success"] is True

    saved = (tmp_path / "customized" / f"{SITE}_gherkin.feature").read_text(encoding="utf-8")
    assert saved == "Feature: edited\n"


def test_api_save_document_schema_validation_failure(tmp_path):
    _write_original(tmp_path, "coverage", "json", "{}")
    client = _app(tmp_path).test_client()

    response = client.post(
        f"/api/{SITE}/documents/coverage.json",
        json={"content": "{}"}
    )
    assert response.status_code == 400
    data = json.loads(response.get_data(as_text=True))
    assert data["success"] is False
    assert "Schema validation failed" in data["error"]
    assert isinstance(data["error_path"], list)


def test_api_save_colors_patches_tokens_json(tmp_path):
    _write_original(tmp_path, "tokens", "json",
                    '{"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    client = _app(tmp_path).test_client()

    response = client.post(
        f"/api/{SITE}/tokens/colors",
        json={"core.color.surface-1": "#0000ff"}
    )
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert data["success"] is True

    saved = (tmp_path / "customized" / f"{SITE}_tokens.json").read_text(encoding="utf-8")
    assert '"$value": "#0000ff"' in saved


_REQUIREMENT = {
    "id": "REQ-a4f9000001", "ears_pattern": "event_driven", "syntax_text": "WHEN x, THE SYSTEM SHALL y",
    "confidence": "observed", "derived_from": [], "coverage_ref": {"run_id": "RUN-1"},
    "links": {"screens": [], "endpoints": [], "scenarios": [], "data_entities": [], "depends_on": []},
    "hitl_status": "unreviewed", "open_questions": [],
}


def test_api_save_fields_patches_requirements_json(tmp_path):
    _write_original(tmp_path, "requirements", "json", json.dumps({"requirements": [_REQUIREMENT]}))
    client = _app(tmp_path).test_client()

    response = client.post(
        f"/api/{SITE}/documents/requirements.json/fields",
        json={"entry:0:hitl_status": "approved"}
    )
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert data["success"] is True

    saved = (tmp_path / "customized" / f"{SITE}_requirements.json").read_text(encoding="utf-8")
    assert '"hitl_status": "approved"' in saved


def test_api_chat_returns_reply_and_uses_document_grounding(tmp_path):
    _write_original(tmp_path, "tokens", "json", '{"core": {"color": {"surface-1": '
                    '{"$type": "color", "$value": "#2d7737"}}}, "semantic": {}}')
    _write_original(tmp_path, "export", "json", '{"@graph": ['
                    '{"id": "core.color.surface-1", "type": "Token"}, '
                    '{"id": "example.com/|button.buy", "type": "Componente", '
                    '"usa_token": ["core.color.surface-1"]}]}')
    agent = _StubAgent(reply="Looks safe.")
    client = _app(tmp_path, agent).test_client()

    response = client.post(
        f"/api/{SITE}/chat",
        json={
            "message": "What uses core.color.surface-1?",
            "history": [],
            "context": {"filename": "tokens", "extension": "json"}
        }
    )
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert data["success"] is True
    assert data["reply"] == "Looks safe."

    assert agent.seen_system_instruction is not None
    assert "core.color.surface-1" in agent.seen_system_instruction
    assert "example.com/|button.buy" in agent.seen_system_instruction


def test_finalizar_triggers_shutdown(tmp_path):
    app = _app(tmp_path)
    fake_server_thread = Mock()
    app.config["SERVER_THREAD"] = fake_server_thread
    client = app.test_client()

    response = client.post("/finalizar")
    assert response.status_code == 200

    deadline = time.monotonic() + 1.0
    while not fake_server_thread.shutdown.called and time.monotonic() < deadline:
        time.sleep(0.01)
    fake_server_thread.shutdown.assert_called_once()


def test_api_graph_returns_export_graph(tmp_path):
    # Kùzu database file to satisfy store resolution
    (tmp_path / f"{SITE}.lbdb").write_text("", encoding="utf-8")
    client = _app(tmp_path).test_client()

    response = client.get(f"/api/{SITE}/graph")
    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert "@context" in data
    assert "@graph" in data


