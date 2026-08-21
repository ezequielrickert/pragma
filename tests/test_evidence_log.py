"""Unit tests for generators/evidence_log.py - pure functions over the
store's own get_interaction_evidence()/get_request_evidence() rows."""
import json

from core.documents import DocumentRequest
from generators.evidence_log import EvidenceLogDocument, build_evidence_log


class _Store:
    def __init__(self, interactions=(), requests=()):
        self._interactions = list(interactions)
        self._requests = list(requests)

    def get_interaction_evidence(self):
        return self._interactions

    def get_request_evidence(self):
        return self._requests


def _interaction(id=1, page_url="shop.example/cart", path="input#q", action="fill", value="DESC10"):
    return {"id": id, "page_url": page_url, "path": path, "action": action, "value": value}


def _request(id=1, method="POST", path="/api/checkout", status=201, host="shop.example", path_pattern="/api/checkout"):
    return {"id": id, "method": method, "path": path, "status": status, "host": host, "path_pattern": path_pattern}


def _request_for(interactions=(), requests=(), run_id="RUN-1"):
    store = _Store(interactions, requests)
    return DocumentRequest(graph_store=store, site="shop.example", agent=None, settings={"run_id": run_id})


# --- build_evidence_log ---

def test_an_interaction_becomes_a_correctly_shaped_row():
    rows = build_evidence_log(_request_for(interactions=[_interaction(id=42)], run_id="RUN-7"))

    assert rows == [{
        "id": "interaction:42", "kind": "interaction", "run_id": "RUN-7",
        "summary": "fill 'DESC10' on input#q (shop.example/cart)",
    }]


def test_a_request_becomes_a_correctly_shaped_row():
    rows = build_evidence_log(_request_for(requests=[_request(id=17)], run_id="RUN-7"))

    assert rows == [{
        "id": "har:17", "kind": "har", "run_id": "RUN-7",
        "summary": "POST shop.example/api/checkout -> 201",
    }]


def test_a_click_with_no_value_has_a_summary_with_no_dangling_quotes():
    rows = build_evidence_log(_request_for(interactions=[_interaction(action="click", value="")]))

    assert rows[0]["summary"] == "click on input#q (shop.example/cart)"


def test_a_request_with_no_status_has_no_arrow_in_its_summary():
    """A request that never got a response is real evidence too - the
    summary must not claim a status that was never observed."""
    rows = build_evidence_log(_request_for(requests=[_request(status=None)]))

    assert "->" not in rows[0]["summary"]


def test_a_request_with_no_endpoint_falls_back_to_the_raw_path():
    rows = build_evidence_log(_request_for(requests=[_request(host=None, path_pattern=None, path="/track")]))

    assert "/track" in rows[0]["summary"]


def test_interaction_rows_come_before_request_rows():
    rows = build_evidence_log(_request_for(interactions=[_interaction(id=1)], requests=[_request(id=1)]))

    assert [row["kind"] for row in rows] == ["interaction", "har"]


def test_an_empty_crawl_produces_an_empty_log():
    assert build_evidence_log(_request_for()) == []


# --- the document ---

def test_generate_writes_one_json_object_per_line():
    outputs = EvidenceLogDocument().outputs(
        _request_for(interactions=[_interaction(id=1)], requests=[_request(id=1)])
    )

    lines = outputs[0].content.splitlines()
    assert len(lines) == 2
    for line in lines:
        row = json.loads(line)
        assert set(row) == {"id", "kind", "run_id", "summary"}


def test_generate_validates_against_the_schema():
    """No exception is the real assertion - generate() calls
    validate_against_schema internally."""
    outputs = EvidenceLogDocument().outputs(_request_for(interactions=[_interaction()]))

    assert outputs[0].content


def test_an_empty_crawl_produces_an_empty_file_not_an_error():
    outputs = EvidenceLogDocument().outputs(_request_for())

    assert outputs[0].content == ""


def test_the_document_declares_a_jsonl_source_output():
    outputs = EvidenceLogDocument().outputs(_request_for())

    assert outputs[0].kind == "source"
    assert outputs[0].extension == "jsonl"
