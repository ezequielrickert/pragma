"""Unit tests for generators/flows_arazzo.py - the Arazzo workflow half
of docs/adr/0014 and the folded-in sequence diagrams (point 4)."""
from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from generators.flows_arazzo import build_arazzo_document, render_flows_sequence_diagrams

PAGE = "shop.example/cart"
ENDPOINT = "shop.example/api/checkout"


def _component(path, text, interactions, requests=()):
    return {
        "page_url": PAGE, "path": path, "text": text, "component_type": "button",
        "interactions": list(interactions), "network_requests": list(requests),
    }


def _interaction(action="click", value="", resulting_url="", visit_id="v1", step_seq=1):
    return {
        "action": action, "value": value, "resulting_url": resulting_url,
        "source_path": "", "visit_id": visit_id, "step_seq": step_seq,
    }


def _request(status=201, visit_id="v1", step_seq=1, failed=False):
    return {
        "method": "POST", "url": f"https://{ENDPOINT}", "status": status,
        "failed": failed, "visit_id": visit_id, "step_seq": step_seq,
    }


def _inferred_request(**overrides):
    defaults = dict(
        method="POST", endpoint=ENDPOINT, query_params=(), body_shape="", response_shape="",
        triggered_by=(), loaded_by=(), status_codes=(),
    )
    defaults.update(overrides)
    return InferredRequest(**defaults)


class _Store:
    def __init__(self, ledger, inferred_requests=()):
        self._ledger = ledger
        self._inferred_requests = list(inferred_requests)

    def get_component_ledger(self):
        return self._ledger

    def get_inferred_requests(self):
        return self._inferred_requests


def _checkout_trace():
    return {
        PAGE: {
            "div>pay": _component(
                "div>pay", "Pagar", [_interaction(resulting_url="shop.example/receipt")],
                [_request()],
            ),
        }
    }


def _request_for(ledger, inferred_requests=()):
    return DocumentRequest(graph_store=_Store(ledger, inferred_requests), site="shop.example", agent=None)


# --- build_arazzo_document ---

def test_a_correlated_trace_becomes_one_workflow_with_a_real_operation_id():
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    document = build_arazzo_document(_request_for(_checkout_trace(), inferred))

    assert document["arazzo"] == "1.1.0"
    assert len(document["workflows"]) == 1
    step = document["workflows"][0]["steps"][0]
    assert step["operationId"] == "createCheckout"


def test_the_success_criterion_is_the_step_s_own_observed_status():
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    document = build_arazzo_document(_request_for(_checkout_trace(), inferred))

    step = document["workflows"][0]["steps"][0]
    assert step["successCriteria"] == [{"condition": "$statusCode == 201"}]


def test_a_failed_request_with_no_status_omits_success_criteria_rather_than_guessing():
    ledger = {
        PAGE: {
            "div>pay": _component(
                "div>pay", "Pagar", [_interaction(resulting_url="shop.example/receipt")],
                [_request(status=None, failed=True)],
            ),
        }
    }
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    document = build_arazzo_document(_request_for(ledger, inferred))

    step = document["workflows"][0]["steps"][0]
    assert "successCriteria" not in step


def test_the_jsonpath_criterion_is_never_emitted():
    """A real, structural gap (see the module docstring): no per-status
    response-body example exists in this crawl's capture model to
    correlate a field's value against."""
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    document = build_arazzo_document(_request_for(_checkout_trace(), inferred))

    step = document["workflows"][0]["steps"][0]
    types = [c.get("type") for c in step.get("successCriteria", [])]
    assert "jsonpath" not in types


def test_an_uncorrelated_trace_produces_no_workflow():
    """No InferredRequest matches this trace's own steps - an empty
    workflow would describe no call sequence at all."""
    document = build_arazzo_document(_request_for(_checkout_trace(), inferred_requests=[]))

    assert document["workflows"] == []


def test_a_request_the_trace_never_triggered_does_not_appear():
    unrelated = _inferred_request(endpoint="shop.example/api/other", triggered_by=((PAGE, "div>other"),))

    document = build_arazzo_document(_request_for(_checkout_trace(), [unrelated]))

    assert document["workflows"] == []


def test_source_descriptions_point_at_the_real_openapi_document():
    document = build_arazzo_document(_request_for({}, []))

    assert document["sourceDescriptions"] == [{"name": "openapi", "url": "./openapi.yaml", "type": "openapi"}]


# --- render_flows_sequence_diagrams ---

def test_every_observable_trace_gets_its_own_diagram_section():
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    section = render_flows_sequence_diagrams(_request_for(_checkout_trace(), inferred))

    assert "## Sequence Diagrams" in section
    assert "sequenceDiagram" in section
    assert f"{PAGE} -> shop.example/receipt" in section


def test_an_uncorrelated_trace_still_gets_a_diagram():
    """Still a real observed sequence, even though nothing in it maps to
    a citable OpenAPI operation - excluded from flows.arazzo.json, not
    from the diagram section."""
    section = render_flows_sequence_diagrams(_request_for(_checkout_trace(), inferred_requests=[]))

    assert "sequenceDiagram" in section


def test_no_traces_says_so_rather_than_an_empty_section():
    section = render_flows_sequence_diagrams(_request_for({}, []))

    assert "No ordered interaction traces" in section
