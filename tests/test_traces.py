"""Unit tests for generators/traces.py - trace construction and the
sequence-diagram rendering `sequences` used to back before folding into
`flows.md` (docs/adr/0014 point 4, ticket #108)."""
from generators.traces import build_traces, render_sequence_diagram, requests_for

PAGE = "shop/cart"


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


def _request(status=201, visit_id="v1", step_seq=1, failed=False, url="https://api/x/checkout"):
    return {"method": "POST", "url": url, "status": status, "failed": failed, "visit_id": visit_id, "step_seq": step_seq}


def _ledger_components():
    return [
        _component("input#q", "Cupon", [_interaction(action="fill", value="DESC10", step_seq=1)]),
        _component("div > pay", "Pagar",
                   [_interaction(resulting_url="shop/receipt", step_seq=2)],
                   [_request(step_seq=2)]),
    ]


# --- build_traces / requests_for ---

def test_steps_are_ordered_by_their_recorded_position():
    """The whole point: "+ + -" and "- + +" were indistinguishable before."""
    components = [
        _component("b", "Second", [_interaction(step_seq=2)]),
        _component("a", "First", [_interaction(step_seq=1)]),
    ]

    trace = build_traces(components)[0]

    assert [step.label for step in trace.steps] == ["First", "Second"]


def test_interactions_from_different_visits_are_different_traces():
    components = [
        _component("a", "A", [_interaction(visit_id="v1", step_seq=1)]),
        _component("b", "B", [_interaction(visit_id="v2", step_seq=1)]),
    ]

    assert len(build_traces(components)) == 2


def test_unstamped_interactions_are_skipped_entirely():
    """They carry no position, so including them would place them
    arbitrarily in a sequence whose whole value is its order."""
    components = [_component("a", "A", [{"action": "click", "visit_id": "", "step_seq": 0}])]

    assert build_traces(components) == []


def test_a_request_is_attributed_to_the_interaction_that_fired_it():
    component = _component("a", "Pay", [], [_request(step_seq=1), _request(status=422, step_seq=2)])

    assert [r["status"] for r in requests_for(component, "v1", 1)] == [201]
    assert [r["status"] for r in requests_for(component, "v1", 2)] == [422]


def test_unstamped_requests_fall_back_to_the_whole_pool():
    """Old data: an unattributable request is still evidence, and returning
    nothing would silently drop it."""
    component = _component("a", "Pay", [], [{"method": "POST", "url": "u", "status": 201}])

    assert len(requests_for(component, "v1", 1)) == 1


# --- render_sequence_diagram ---

def test_the_diagram_shows_the_actor_the_ui_and_the_api():
    trace = build_traces(_ledger_components())[0]

    diagram = render_sequence_diagram(trace)

    assert "sequenceDiagram" in diagram
    assert "User->>UI: fill" in diagram
    assert "UI->>API: POST https://api/x/checkout" in diagram
    assert "API-->>UI: 201" in diagram


def test_a_failed_request_is_drawn_as_a_failure_not_a_blank():
    components = [_component("a", "Pay", [_interaction(resulting_url="shop/x")],
                             [_request(status=None, failed=True)])]

    diagram = render_sequence_diagram(build_traces(components)[0])

    assert "API-->>UI: request failed" in diagram
