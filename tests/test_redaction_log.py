"""Unit tests for generators/redaction_log.py - consolidating openapi's
Overlay redaction events into redaction-log.jsonl (docs/adr/0021)."""
import json

import pytest

from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from generators.redaction_log import RedactionLogDocument, build_redaction_log
from utils.schema_validation import validate_against_schema

pytest.importorskip("openapi_spec_validator")

_SCHEMA_PATH = "schemas/redaction-log.schema.json"


def _request(method="GET", endpoint="api.example.com/orders", **extra):
    defaults = dict(
        query_params=(), body_shape="", response_shape="", triggered_by=(),
        loaded_by=(), status_codes=(200,), latencies_ms=(),
    )
    defaults.update(extra)
    return InferredRequest(method=method, endpoint=endpoint, **defaults)


class _Store:
    def __init__(self, requests):
        self._requests = requests

    def get_inferred_requests(self):
        return self._requests


def _document_request(requests, overlay_actions):
    """A DocumentRequest whose openapi document is real (built from
    `requests`) and whose overlay is the exact actions under test -
    settings carries the run_id, matching evidence_log.py's own
    settings-based run_id convention."""
    return DocumentRequest(
        graph_store=_Store(requests), site="example.com", agent=None,
        settings={"run_id": "RUN-1", "overlay_actions": overlay_actions},
    )


def _build(monkeypatch, requests, overlay_actions):
    """Builds the log with `load_overlay` redirected to exactly the actions
    under test, rather than reading config/redaction.overlay.yaml (which
    ships empty by default) - each test's overlay is what it declares,
    nothing else."""
    import generators.redaction_log as redaction_log_module

    monkeypatch.setattr(
        redaction_log_module, "load_overlay",
        lambda: {"overlay": "1.0.0", "actions": overlay_actions},
    )
    request = _document_request(requests, overlay_actions)
    return build_redaction_log(request)


def test_an_action_that_matches_nothing_produces_no_row(monkeypatch):
    rows = _build(monkeypatch, [_request()], [{"target": "$.paths['/never/matches'].get", "remove": True}])

    assert rows == []


def test_a_matching_remove_action_produces_one_row_citing_the_concrete_field(monkeypatch):
    requests = [_request(response_shape=json.dumps({"id": "string"}))]
    action = {"target": "$.paths['/orders'].get.responses.200.description", "remove": True, "description": "internal note"}

    rows = _build(monkeypatch, requests, [action])

    assert len(rows) == 1
    row = rows[0]
    assert row["field_path"] == "$.paths['/orders'].get.responses.200.description"
    assert row["source_document"] == "openapi"
    assert row["reason"] == "internal note"
    assert row["run_id"] == "RUN-1"


def test_a_wildcard_action_produces_one_row_per_concrete_match(monkeypatch):
    requests = [
        _request(endpoint="api.example.com/orders"),
        _request(endpoint="api.example.com/carts"),
    ]
    action = {"target": "$.paths[*][*].summary", "remove": True}

    rows = _build(monkeypatch, requests, [action])

    field_paths = {row["field_path"] for row in rows}
    assert len(rows) == len(field_paths) == 2


def test_a_description_less_action_has_an_honest_empty_reason_not_an_invented_one(monkeypatch):
    requests = [_request()]
    action = {"target": "$.paths['/orders'].get.summary", "remove": True}

    rows = _build(monkeypatch, requests, [action])

    assert rows[0]["reason"] == ""


def test_evidence_names_the_raw_and_public_artifacts_never_the_value(monkeypatch):
    requests = [_request()]
    action = {"target": "$.paths['/orders'].get.summary", "update": "top secret internal value"}

    rows = _build(monkeypatch, requests, [action])

    row = rows[0]
    assert row["evidence"] == {"raw_artifact": "openapi.raw", "public_artifact": "openapi"}
    assert "top secret internal value" not in json.dumps(row)


def test_no_overlay_actions_means_an_empty_log_not_an_error(monkeypatch):
    rows = _build(monkeypatch, [_request()], [])

    assert rows == []


def test_the_log_validates_against_its_own_schema(monkeypatch):
    action = {"target": "$.paths['/orders'].get.summary", "remove": True}

    rows = _build(monkeypatch, [_request()], [action])

    validate_against_schema(rows, _SCHEMA_PATH)


def test_generate_returns_one_jsonl_source_output(monkeypatch):
    import generators.redaction_log as redaction_log_module

    action = {"target": "$.paths['/orders'].get.summary", "remove": True}
    monkeypatch.setattr(redaction_log_module, "load_overlay", lambda: {"overlay": "1.0.0", "actions": [action]})
    request = _document_request([_request()], [action])

    outputs = RedactionLogDocument().outputs(request)

    assert len(outputs) == 1
    assert outputs[0].kind == "source" and outputs[0].extension == "jsonl"
    row = json.loads(outputs[0].content.strip())
    assert row["field_path"] == "$.paths['/orders'].get.summary"
