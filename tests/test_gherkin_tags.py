"""Unit tests for generators/gherkin_tags.py - the store-dependent half of
docs/adr/0013 (correlating a trace to requirements.py's extraction rules
and to the graph's module/screen ids)."""
from core.interfaces import InferredRequest
from generators.gherkin_tags import (
    TraceCorrelations,
    _endpoint_tag_id,
    _screen_tag_id,
    correlate_trace,
    module_tags,
    tag_line,
    trace_screens,
)
from generators.requirements import requirement_id
from generators.traces import build_traces

PAGE = "shop/cart"
ENDPOINT = "shop/api/checkout"


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
    def __init__(self, inferred_requests=()):
        self._inferred_requests = list(inferred_requests)

    def get_inferred_requests(self):
        return self._inferred_requests


def _ledger_components():
    return [
        _component("input#q", "Cupon", [_interaction(action="fill", value="DESC10", step_seq=1)]),
        _component("div > pay", "Pagar",
                   [_interaction(resulting_url="shop/receipt", step_seq=2)],
                   [_request(step_seq=2)]),
    ]


# --- correlate_trace ---

def test_event_driven_correlation_tags_the_triggering_interaction():
    trace = build_traces(_ledger_components())[0]
    inferred = [_inferred_request(triggered_by=((PAGE, "div > pay"),))]

    correlations = correlate_trace(_Store(inferred), trace)

    expected_req = requirement_id(
        "event_driven", "the user interacts with div > pay on shop/cart", f"POST {ENDPOINT}"
    )
    assert correlations.requirement_ids == (expected_req,)
    assert correlations.endpoint_ids == (_endpoint_tag_id(f"POST {ENDPOINT}"),)


def test_ubiquitous_correlation_matches_by_start_page_not_a_specific_step():
    trace = build_traces(_ledger_components())[0]
    inferred = [_inferred_request(loaded_by=(PAGE,))]

    correlations = correlate_trace(_Store(inferred), trace)

    assert len(correlations.requirement_ids) == 1
    assert correlations.requirement_ids[0].startswith("REQ-")


def test_unwanted_behavior_only_applies_to_an_endpoint_this_trace_touched():
    """A failure on an endpoint this trace never called is not this
    trace's own requirement."""
    trace = build_traces(_ledger_components())[0]
    untouched_failure = _inferred_request(endpoint="shop/api/other", status_codes=(500,))

    correlations = correlate_trace(_Store([untouched_failure]), trace)

    assert correlations.requirement_ids == ()
    assert correlations.endpoint_ids == ()


def test_unwanted_behavior_adds_a_third_requirement_when_the_touched_call_failed():
    trace = build_traces(_ledger_components())[0]
    inferred = [_inferred_request(triggered_by=((PAGE, "div > pay"),), status_codes=(422,))]

    correlations = correlate_trace(_Store(inferred), trace)

    assert len(correlations.requirement_ids) == 2  # event_driven + unwanted_behavior


def test_a_step_with_no_matching_inferred_request_correlates_to_nothing():
    trace = build_traces(_ledger_components())[0]

    correlations = correlate_trace(_Store([]), trace)

    assert correlations.requirement_ids == () and correlations.endpoint_ids == ()


# --- screens and modules ---

def test_trace_screens_lists_the_start_page_and_every_navigation_destination():
    trace = build_traces(_ledger_components())[0]

    assert trace_screens(trace) == (PAGE, "shop/receipt")


def test_module_tags_are_empty_without_module_data():
    trace = build_traces(_ledger_components())[0]

    assert module_tags({}, trace) == ()


def test_module_tags_resolve_through_every_visited_screen():
    trace = build_traces(_ledger_components())[0]
    module_ids = {_screen_tag_id(PAGE): "MOD-cart", _screen_tag_id("shop/receipt"): "MOD-receipt"}

    assert module_tags(module_ids, trace) == ("MOD-cart", "MOD-receipt")


# --- tag_line ---

def test_tag_line_always_carries_req_and_confidence_first():
    line = tag_line(TraceCorrelations(requirement_ids=("REQ-abc",), endpoint_ids=()), (), ())

    assert line == "  @REQ-abc @confidence:observed"


def test_tag_line_appends_optional_tags_in_order():
    line = tag_line(
        TraceCorrelations(requirement_ids=("REQ-a",), endpoint_ids=("EP-b",)), ("MOD-c",), ("SCR-d",)
    )

    assert line == "  @REQ-a @confidence:observed @EP-b @MOD-c @SCR-d"
