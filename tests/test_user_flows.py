"""Unit tests for the user-flow state machine and its XState export
(generators/user_flows.py). Pure functions over hand-built edges and
ledger rows. The Arazzo half has its own tests in
tests/test_flows_arazzo.py."""
from generators.user_flows import (
    ERROR,
    OK,
    UNKNOWN,
    build_flow_graph,
    build_xstate_document,
    render_state_diagram,
)
from utils.short_hash import short_hash


def _edge(from_state="/shop", to_state="/checkout", path="div > button", action="click"):
    return {"from": from_state, "component": path, "action": action, "to": to_state}


def _component(page="/shop", path="div > button", text="Comprar", requests=None, to_state="/checkout"):
    """A `Request` only ever exists hung off a specific `Interaction` in
    the real graph (see `database/ladybug/network.py`), never pooled
    loose on a `Component` - so each of `requests` gets its own matching,
    stamped interaction here, one visit ("v1"), sequential steps, all
    resulting in `to_state` (the edge target most of this file's cases
    share `_edge()`'s own default for)."""
    requests = requests or []
    return {
        "page_url": page, "path": path, "text": text, "component_type": "button",
        "interactions": [
            {"action": "click", "resulting_url": to_state, "visit_id": "v1", "step_seq": i + 1}
            for i in range(len(requests))
        ],
        "network_requests": [
            {**r, "visit_id": "v1", "step_seq": i + 1} for i, r in enumerate(requests)
        ],
    }


def _request(status=201, failed=False, method="POST", path="https://api/x/orders"):
    return {"method": method, "path": path, "status": status, "failed": failed}


# --- transitions ---

def test_a_transition_is_labelled_with_the_control_a_person_would_name():
    flow = build_flow_graph([_edge()], [_component(text="Comprar")])

    assert flow.transitions[0].trigger == "Comprar"


def test_a_control_with_no_text_falls_back_to_its_role():
    flow = build_flow_graph([_edge()], [_component(text="")])

    assert flow.transitions[0].trigger == "button"


def test_a_control_with_neither_text_nor_role_falls_back_to_its_path():
    """The path is then the only honest answer, and also the thing to go
    look at."""
    component = _component(text="")
    component["component_type"] = ""

    flow = build_flow_graph([_edge()], [component])

    assert flow.transitions[0].trigger == "div > button"


def test_an_unknown_component_still_produces_a_transition():
    """A navigation edge without a matching ledger row is real history; it
    must not vanish from the diagram just because its label is poorer."""
    flow = build_flow_graph([_edge()], [])

    assert flow.transitions[0].trigger == "div > button"
    assert flow.transitions[0].outcome == UNKNOWN


def test_repeated_navigations_collapse_into_one_transition():
    """record_edge uses CREATE, so a page visited twice writes the edge
    twice - real history in the store, noise in a state machine."""
    flow = build_flow_graph([_edge(), _edge(), _edge()], [_component()])

    assert len(flow.transitions) == 1


# --- outcomes ---

def test_the_endpoint_and_status_come_from_the_triggering_component():
    flow = build_flow_graph([_edge()], [_component(requests=[_request(status=201)])])

    transition = flow.transitions[0]
    assert transition.endpoint == "POST https://api/x/orders"
    assert transition.status == 201
    assert transition.outcome == OK


def test_a_4xx_response_marks_the_transition_as_an_error_branch():
    """The 422 branch is the reason to read this document at all."""
    flow = build_flow_graph([_edge()], [_component(requests=[_request(status=422)])])

    assert flow.transitions[0].outcome == ERROR


def test_a_failed_request_is_an_error_even_with_no_status():
    flow = build_flow_graph([_edge()], [_component(requests=[_request(status=None, failed=True)])])

    assert flow.transitions[0].outcome == ERROR
    assert flow.transitions[0].status is None


def test_a_failure_wins_over_a_success_on_the_same_control():
    """A control that answers 201 for most inputs and 422 for some is
    interesting because of the 422 - summarising by the happy path hides
    exactly the branch worth documenting."""
    flow = build_flow_graph(
        [_edge()], [_component(requests=[_request(status=201), _request(status=422)])]
    )

    assert flow.transitions[0].outcome == ERROR
    assert flow.transitions[0].status == 422


# --- shape of the machine ---

def test_entry_states_are_the_ones_nothing_leads_into():
    flow = build_flow_graph(
        [_edge("/shop", "/checkout"), _edge("/checkout", "/receipt", path="div > pay")],
        [_component(), _component("/checkout", "div > pay", "Pagar")],
    )

    assert flow.entry_states == ("/shop",)


def test_dead_ends_are_the_ones_nothing_leads_out_of():
    flow = build_flow_graph([_edge("/shop", "/checkout")], [_component()])

    assert flow.dead_ends == ("/checkout",)


def test_states_are_deduplicated_across_transitions():
    flow = build_flow_graph(
        [_edge("/shop", "/checkout"), _edge("/shop", "/checkout", path="div > b2")],
        [_component(), _component(path="div > b2", text="Comprar ya")],
    )

    assert flow.states == ("/checkout", "/shop")
    assert len(flow.transitions) == 2


def test_an_empty_crawl_produces_an_empty_machine():
    flow = build_flow_graph([], [])

    assert flow.states == () and flow.transitions == ()


# --- rendering ---

def test_the_diagram_uses_token_ids_and_carries_the_real_route_as_a_label():
    """Mermaid state identifiers must be plain tokens; real routes are not."""
    flow = build_flow_graph([_edge("/shop/{id}", "/checkout")], [_component("/shop/{id}")])

    diagram = render_state_diagram(flow)

    assert "s0 : /checkout" in diagram
    assert "s1 --> s0" in diagram or "s0 --> s1" in diagram


def test_the_diagram_marks_error_branches():
    flow = build_flow_graph([_edge()], [_component(requests=[_request(status=422)])])

    assert "[error]" in render_state_diagram(flow)


def test_entry_states_get_a_start_marker():
    flow = build_flow_graph([_edge("/shop", "/checkout")], [_component()])

    assert "[*] -->" in render_state_diagram(flow)


def test_a_trigger_with_a_colon_does_not_break_the_diagram_syntax():
    """A colon separates a Mermaid state id from its label - one inside a
    button's text would silently corrupt the line."""
    flow = build_flow_graph([_edge()], [_component(text="Total: 500")])

    line = next(l for l in render_state_diagram(flow).splitlines() if "-->" in l and "[*]" not in l)

    assert line.count(":") == 1


# --- XState export (ADR-0014 point 1/2) ---

def test_every_state_carries_its_real_screen_id():
    flow = build_flow_graph([_edge("/shop", "/checkout")], [_component()])

    machine = build_xstate_document(flow, "shop.example")

    for state in machine["states"].values():
        assert state["meta"]["screen"].startswith("SCR-")


def test_a_single_destination_needs_no_guard():
    flow = build_flow_graph([_edge("/shop", "/checkout")], [_component()])

    machine = build_xstate_document(flow, "shop.example")

    origin = next(state for state in machine["states"].values() if "on" in state)
    (transition,) = origin["on"].values()
    assert "target" in transition and "guard" not in transition


def test_two_destinations_for_the_same_trigger_produce_guarded_branches():
    """The crawl actually observed the same control leading to two
    different screens - a real branch to document, not one invented."""
    edges = [_edge("/cart", "/receipt", path="div > pay"), _edge("/cart", "/cart", path="div > pay")]
    component = {
        "page_url": "/cart", "path": "div > pay", "text": "Pagar", "component_type": "button",
        "interactions": [
            {"action": "click", "resulting_url": "/receipt", "visit_id": "v1", "step_seq": 1},
            {"action": "click", "resulting_url": "/cart", "visit_id": "v1", "step_seq": 2},
        ],
        "network_requests": [
            {**_request(status=201), "visit_id": "v1", "step_seq": 1},
            {**_request(status=422), "visit_id": "v1", "step_seq": 2},
        ],
    }
    flow = build_flow_graph(edges, [component])

    machine = build_xstate_document(flow, "shop.example")

    cart_state_id = next(
        sid for sid, s in machine["states"].items() if s["meta"]["screen"] == f"SCR-{short_hash('/cart')}"
    )
    (branches,) = machine["states"][cart_state_id]["on"].values()
    assert len(branches) == 2
    assert {b["guard"]["type"] for b in branches} == {OK, ERROR}
    assert all(b["guard"]["params"]["derived_from"] == [] for b in branches)


def test_the_initial_state_is_a_real_entry_state():
    flow = build_flow_graph([_edge("/shop", "/checkout")], [_component()])

    machine = build_xstate_document(flow, "shop.example")

    assert machine["initial"] in machine["states"]


def test_an_empty_flow_produces_no_initial_state():
    flow = build_flow_graph([], [])

    machine = build_xstate_document(flow, "shop.example")

    assert "initial" not in machine
    assert machine["states"] == {}


# --- document ---

def test_the_view_reports_error_branches_and_dead_ends():
    from core.documents import DocumentRequest
    from generators.user_flows import FlowsDocument

    class _Store:
        def get_edges(self):
            return [_edge()]

        def get_component_ledger(self):
            return {"/shop": {"div > button": _component(requests=[_request(status=422)])}}

        def get_inferred_requests(self):
            return []

    view = FlowsDocument().outputs(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )[2].content

    assert "Error branches" in view
    assert "Screens with no way out" in view
    assert "/checkout" in view


def test_a_crawl_with_no_navigation_says_so_instead_of_drawing_nothing():
    from core.documents import DocumentRequest
    from generators.user_flows import FlowsDocument

    class _Store:
        def get_edges(self):
            return []

        def get_component_ledger(self):
            return {}

        def get_inferred_requests(self):
            return []

    view = FlowsDocument().outputs(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )[2].content

    assert "no navigation" in view


def test_generate_returns_xstate_arazzo_and_view_outputs():
    from core.documents import DocumentRequest
    from generators.user_flows import FlowsDocument
    import json

    class _Store:
        def get_edges(self):
            return [_edge()]

        def get_component_ledger(self):
            return {"/shop": {"div > button": _component()}}

        def get_inferred_requests(self):
            return []

    outputs = FlowsDocument().outputs(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert [o.filename for o in outputs] == ["flows.xstate", "flows.arazzo", "flows"]
    assert [(o.kind, o.extension) for o in outputs] == [
        ("source", "json"), ("source", "json"), ("view", "md"),
    ]
    json.loads(outputs[0].content)
    json.loads(outputs[1].content)


def test_one_control_leading_to_two_screens_with_agreeing_requests_keeps_its_outcome():
    """No ambiguity to resolve when every request the control fired failed -
    both destinations should read as the same clear ERROR."""
    edges = [
        _edge("/cart", "/receipt", path="div > pay"),
        _edge("/cart", "/cart", path="div > pay"),
    ]
    component = {
        "page_url": "/cart", "path": "div > pay", "text": "Pagar", "component_type": "button",
        "interactions": [
            {"action": "click", "resulting_url": "/receipt", "visit_id": "v1", "step_seq": 1},
            {"action": "click", "resulting_url": "/cart", "visit_id": "v1", "step_seq": 2},
        ],
        "network_requests": [
            {**_request(status=422), "visit_id": "v1", "step_seq": 1},
            {**_request(status=500), "visit_id": "v1", "step_seq": 2},
        ],
    }

    flow = build_flow_graph(edges, [component])

    assert {t.outcome for t in flow.transitions} == {ERROR}


def test_one_control_leading_to_two_screens_keeps_each_destinations_own_outcome():
    """Requests sit on the interaction that fired them, not pooled on the
    control - the successful branch keeps its 201 and the failed one its
    422, never both labelled with the other's status."""
    edges = [
        _edge("/cart", "/receipt", path="div > pay"),
        _edge("/cart", "/cart", path="div > pay"),
    ]
    component = {
        "page_url": "/cart", "path": "div > pay", "text": "Pagar", "component_type": "button",
        "interactions": [
            {"action": "click", "resulting_url": "/receipt", "visit_id": "v1", "step_seq": 1},
            {"action": "click", "resulting_url": "/cart", "visit_id": "v1", "step_seq": 2},
        ],
        "network_requests": [
            {**_request(status=201), "visit_id": "v1", "step_seq": 1},
            {**_request(status=422), "visit_id": "v1", "step_seq": 2},
        ],
    }

    flow = build_flow_graph(edges, [component])
    by_destination = {t.to_state: t for t in flow.transitions}

    assert by_destination["/receipt"].outcome == OK
    assert by_destination["/receipt"].status == 201
    assert by_destination["/cart"].outcome == ERROR
    assert by_destination["/cart"].status == 422
