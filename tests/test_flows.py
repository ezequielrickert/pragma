"""Unit tests for Flow derivation (generators/flows.py) - pure functions
over hand-built ledger rows - plus the semantic tier's Flow write path
(database/ladybug/flow.py) against the real engine, same discipline as
test_screens.py.
"""
from __future__ import annotations

import pytest

from core.interfaces import InferredRequest, SemanticEntity, SemanticField, SemanticFlow, VisitStep
from database.ladybug.store import LadybugGraphStore
from generators.flows import build_flows
from generators.ledger import flat_component_ledger
from generators.screens import build_screens

PAGE = "shop.example/cart"
RECEIPT = "shop.example/receipt"
ENDPOINT = "shop.example/api/orders"


def _component(path, interactions, requests=(), page_url=PAGE):
    return {
        "page_url": page_url, "path": path, "text": "Pagar", "component_type": "button",
        "interactions": list(interactions), "network_requests": list(requests),
    }


def _interaction(action="click", resulting_url="", visit_id="v1", step_seq=1):
    return {
        "action": action, "value": "", "resulting_url": resulting_url,
        "source_path": "", "visit_id": visit_id, "step_seq": step_seq,
    }


def _request(status=201, visit_id="v1", step_seq=1, failed=False, method="POST", path="/orders"):
    return {
        "method": method, "url": f"https://{ENDPOINT}{path}", "path": path, "status": status,
        "failed": failed, "visit_id": visit_id, "step_seq": step_seq,
    }


def _inferred_request(**overrides):
    defaults = dict(
        method="POST", endpoint=ENDPOINT, query_params=(), body_shape="", response_shape="",
        triggered_by=(), loaded_by=(), status_codes=(),
    )
    defaults.update(overrides)
    return InferredRequest(**defaults)


# --- build_flows: name/goal cascade ---

def test_a_correlated_terminal_request_names_the_flow_after_its_operation():
    components = [_component("div>pay", [_interaction()], [_request()])]
    inferred = [_inferred_request(triggered_by=((PAGE, "div>pay"),))]

    flow = build_flows(components, inferred)[0]

    assert flow.name == "Create order"
    assert flow.goal == "Create order (POST shop.example/api/orders)"


@pytest.mark.parametrize(
    ("path", "expected_name"),
    [
        ("/account/logout", "Log out"),
        ("/checkout", "Purchase"),
        ("/auth/signup", "Sign up"),
        ("/auth/login", "Log in"),
        ("/products/search", "Search"),
        ("/cart/items/remove", "Delete"),
    ],
)
def test_a_taxonomy_keyword_in_the_endpoint_overrides_the_crud_verb_phrase(path, expected_name):
    endpoint = f"shop.example/api{path}"
    components = [_component("div>pay", [_interaction()], [_request(path=path)])]
    inferred = [_inferred_request(endpoint=endpoint, triggered_by=((PAGE, "div>pay"),))]

    flow = build_flows(components, inferred)[0]

    assert flow.name == expected_name
    assert flow.goal == f"{expected_name} (POST {endpoint})"


def test_taxonomy_override_applies_regardless_of_http_method():
    endpoint = "shop.example/api/session/logout"
    components = [_component("div>pay", [_interaction()], [_request(method="GET", path="/session/logout")])]
    inferred = [_inferred_request(method="GET", endpoint=endpoint, triggered_by=((PAGE, "div>pay"),))]

    flow = build_flows(components, inferred)[0]

    assert flow.name == "Log out"


def test_taxonomy_override_does_not_apply_to_the_tier_2_route_shape_fallback():
    components = [_component("div>pay", [_interaction(resulting_url="shop.example/checkout")])]

    flow = build_flows(components, [])[0]

    assert flow.name == "shop.example/checkout"


def test_no_correlated_request_falls_back_to_the_terminal_route():
    components = [_component("div>pay", [_interaction(resulting_url=RECEIPT)])]

    flow = build_flows(components, [])[0]

    assert flow.name == "shop.example/receipt"
    assert flow.goal == "Reach shop.example/receipt."


def test_a_dead_end_falls_back_to_the_generic_step_count_name():
    components = [_component("div>pay", [_interaction()])]

    flow = build_flows(components, [])[0]

    assert flow.name == flow.goal == "1-step flow from shop.example/cart"


# --- build_flows: outcome/step_count/derived_from ---

def test_outcome_reads_the_terminal_step_own_requests():
    components = [_component("div>pay", [_interaction()], [_request(status=500, failed=True)])]

    flow = build_flows(components, [])[0]

    assert flow.outcome == "error"


def test_a_non_observable_trace_still_gets_a_flow_with_unknown_outcome():
    components = [_component("div>pay", [_interaction()])]

    flow = build_flows(components, [])[0]

    assert flow.outcome == "unknown"
    assert flow.step_count == 1
    assert flow.visit_id == "v1"


def test_derived_from_carries_each_step_own_real_step_seq():
    components = [
        _component("div>a", [_interaction(step_seq=1)]),
        _component("div>b", [_interaction(step_seq=2)]),
    ]

    flow = build_flows(components, [])[0]

    assert flow.step_count == 2
    assert flow.derived_from == (1, 2)


# --- store write path ---

@pytest.fixture
def store():
    instance = LadybugGraphStore("flows.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _record_one_step_trace(store: LadybugGraphStore) -> None:
    store.record_component(PAGE, "div>pay", tag="button", text="Pagar")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction(PAGE, "div>pay", "click", step=step)
    store.record_component_network(
        PAGE, "div>pay",
        [{**_request(status=201), "visit_id": "v1", "step_seq": 1}],
    )


def _built_flows(store: LadybugGraphStore):
    return build_flows(flat_component_ledger(store), store.get_inferred_requests())


def test_the_store_refuses_a_flow_with_no_derived_from(store) -> None:
    orphan = SemanticFlow(visit_id="v1", name="n", goal="g", step_count=0, outcome="unknown", derived_from=())
    with pytest.raises(ValueError):
        store.record_flows([orphan])


def test_flows_round_trip_through_the_store(store) -> None:
    _record_one_step_trace(store)
    original = _built_flows(store)

    store.record_flows(original, run_id="run-1")

    assert store.get_flows() == original


def test_recording_flows_twice_is_a_full_rebuild(store) -> None:
    _record_one_step_trace(store)
    store.record_flows(_built_flows(store), run_id="run-1")

    store.reset()
    store.record_component(PAGE, "div>other", tag="button", text="Other")
    step = VisitStep(visit_id="v2").take()
    store.record_component_interaction(PAGE, "div>other", "click", step=step)
    store.record_flows(_built_flows(store), run_id="run-2")

    assert [f.visit_id for f in store.get_flows()] == ["v2"]


def test_a_flow_step_of_edge_carries_its_sequence(store) -> None:
    _record_one_step_trace(store)
    store.record_flows(_built_flows(store), run_id="run-1")

    def op(conn):
        return list(conn.execute("MATCH (:Interaction)-[e:STEP_OF]->(:Flow) RETURN e.seq"))

    assert store._call(op) == [[1]]


def test_recording_flows_does_not_wipe_screen_provenance(store) -> None:
    _record_one_step_trace(store)
    store.record_screens(build_screens([{"url": PAGE, "status": "Finished", "components": 1}]), run_id="run-1")

    store.record_flows(_built_flows(store), run_id="run-1")

    assert [s.page_url for s in store.get_screens()] == [PAGE]


def test_recording_screens_does_not_wipe_flow_provenance(store) -> None:
    _record_one_step_trace(store)
    store.record_flows(_built_flows(store), run_id="run-1")

    store.record_screens(build_screens([{"url": PAGE, "status": "Finished", "components": 1}]), run_id="run-1")

    assert [f.visit_id for f in store.get_flows()] == ["v1"]


def test_recording_flows_does_not_wipe_entity_provenance(store) -> None:
    _record_one_step_trace(store)
    entity = SemanticEntity(
        name="checkout", description="d",
        fields=(SemanticField(
            name="email", data_type="email", required=True, validation="",
            observed_values=(), derived_from=((PAGE, "#a"),),
        ),),
        derived_from=((PAGE, "#a"),),
    )
    store.record_entities([entity], run_id="run-1")

    store.record_flows(_built_flows(store), run_id="run-1")

    assert [e.name for e in store.get_entities()] == ["checkout"]


def test_the_provenance_edge_records_which_run_and_generator(store) -> None:
    _record_one_step_trace(store)
    store.record_flows(_built_flows(store), run_id="run-7")

    def op(conn):
        return list(conn.execute(
            "MATCH (:Flow)-[e:DERIVED_FROM]->(:Interaction) RETURN e.run_id, e.generator, e.method, e.confidence"
        ))

    assert store._call(op) == [["run-7", "flows.build_flows", "deterministic", 1.0]]
