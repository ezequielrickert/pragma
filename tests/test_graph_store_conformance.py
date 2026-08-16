"""Backend-agnostic `GraphStore` conformance suite.

Every test here runs once per entry in `graph_store_backends.BACKENDS`, so
`memory` and `neo4j` (and any future backend registered there, e.g.
`duckdb`) are all held to the identical contract - a change to one backend
that silently drops a guarantee the other honors now fails here instead of
surfacing as a downstream generator bug only one backend ever hits.

This replaces the ~40 near-identical assertions that used to be duplicated
across `test_graph_store.py` (in-memory) and
`test_neo4j_graph_store_integration.py` (Neo4j), with no mechanism keeping
the two in sync. Only `GraphStore`'s own public methods are called here -
no raw Cypher, no backend-internal state - so a genuinely backend-specific
guarantee (Neo4j Browser captions, dynamic tag labels, the `:Inferred`
marker label) stays out of this file and lives in the backend's own test
file instead.
"""
from __future__ import annotations

import itertools
import json
from typing import Iterator

import pytest

from core.interfaces import ComponentFacts, ComponentFamily, GraphStore, InferredRequest, VisitStep
from tests.graph_store_backends import BACKENDS

_site_counter = itertools.count()


@pytest.fixture(params=sorted(BACKENDS))
def store(request) -> Iterator[GraphStore]:
    factory = BACKENDS[request.param]
    instance = factory()
    if instance is None:
        pytest.skip(f"{request.param} backend unavailable in this environment")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def site(store: GraphStore) -> Iterator[str]:
    """A fresh site namespace per test - not just per backend - so tests
    can never see each other's writes, including on a long-lived shared
    Neo4j instance (tier 1) reused across the whole suite. Cleaned up after
    via the store's own `clear_site`, exercising that method on every
    backend as a side effect of every single test.
    """
    name = f"pragma-conformance-test.local.{next(_site_counter)}"
    yield name
    store.clear_site(name)


def test_upsert_page_pending_never_clobbers_finished(store: GraphStore, site: str) -> None:
    store.upsert_page(site, "x", status="Pending", components=0)
    store.upsert_page(site, "x", status="Finished", components=5)
    store.upsert_page(site, "x", status="Pending", components=0)

    rows = store.get_progress_table_rows(site)
    assert len(rows) == 1
    assert rows[0]["status"] == "Finished"
    assert rows[0]["components"] == 5


def test_is_visited_false_for_unknown_url(store: GraphStore, site: str) -> None:
    assert store.is_visited(site, "never-seen") is False


def test_get_pending_respects_limit_and_order(store: GraphStore, site: str) -> None:
    for i in (3, 1, 2):
        store.upsert_page(site, f"page-{i}")

    assert store.get_pending(site) == ["page-1", "page-2", "page-3"]
    assert store.get_pending(site, limit=2) == ["page-1", "page-2"]


def test_site_isolation(store: GraphStore, site: str) -> None:
    other = f"{site}.other"
    store.upsert_page(site, "shared", status="Pending")
    store.upsert_page(other, "shared", status="Finished")

    assert store.is_visited(site, "shared") is False
    assert store.is_visited(other, "shared") is True
    assert store.get_pending(other) == []

    store.record_edge(site, "home", "about", "link", "GOTO about")
    store.record_edge(other, "home", "about-other", "link", "GOTO about-other")
    assert [e["to"] for e in store.get_edges(site)] == ["about"]
    assert [e["to"] for e in store.get_edges(other)] == ["about-other"]

    store.clear_site(other)


def test_link_label_is_scoped_to_the_specific_from_to_pair(store: GraphStore, site: str) -> None:
    store.record_link(site, "home", "about", "About Us")
    store.record_link(site, "other-page", "about", "Learn more")

    assert store.get_link_label(site, "home", "about") == "About Us"
    assert store.get_link_label(site, "other-page", "about") == "Learn more"
    assert store.get_link_label(site, "unrelated-page", "about") is None


def test_loop_signals_detects_revisit(store: GraphStore, site: str) -> None:
    store.record_edge(site, "home", "contact", 'link "Contact"', "GOTO contact")
    store.record_edge(site, "about", "contact", 'link "Contact us"', "GOTO contact")

    signals = store.get_loop_signals(site, "contact")
    assert len(signals) == 2
    assert {"component": 'link "Contact"', "from": "home"} in signals
    assert store.get_loop_signals(site, "never-reached") == []


def test_clear_site_removes_pages_edges_and_links(store: GraphStore, site: str) -> None:
    store.upsert_page(site, "home", status="Finished")
    store.record_edge(site, "home", "about", 'link "About"', "GOTO about")
    store.record_link(site, "home", "about", "About Us")

    store.clear_site(site)

    assert store.get_progress_table_rows(site) == []
    assert store.get_edges(site) == []
    assert store.get_link_label(site, "home", "about") is None


def test_record_component_idempotent_and_preserves_interacted(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "button#go", tag="button", text="Go")
    store.record_component_interaction(site, "home", "button#go", action="click")
    # A later rediscovery (page revisited) must not clobber the interacted
    # flag or its interaction history - only descriptive fields refresh.
    store.record_component(site, "home", "button#go", tag="button", text="Go (updated)")

    states = store.get_component_states(site, "home")
    assert states["button#go"]["interacted"] is True
    assert states["button#go"]["text"] == "Go (updated)"


def test_record_component_persists_position(store: GraphStore, site: str) -> None:
    store.record_component(
        site, "home", "button#go", tag="button", text="Go",
        x=10.0, y=20.0, width=80.0, height=32.0,
    )
    states = store.get_component_states(site, "home")
    assert states["button#go"]["x"] == 10.0
    assert states["button#go"]["height"] == 32.0

    ledger = store.get_component_ledger(site)
    assert ledger["home"]["button#go"]["width"] == 80.0

    # A caller that doesn't know position (e.g. record_component_interaction's
    # auto-create) must not error - position is just None, not required.
    store.record_component(site, "y", "button#other")
    assert store.get_component_states(site, "y")["button#other"]["x"] is None


def test_record_component_options_persists_clean_labels(store: GraphStore, site: str) -> None:
    raw_json = json.dumps({"group": "flavor", "options": [{"text": "Mi Gusto", "selected": True}]})
    store.record_component_options(site, "home", "combo#1", raw_json, option_labels=["Mi Gusto (selected)"])

    state = store.get_component_states(site, "home")["combo#1"]
    assert state["options"] == raw_json
    assert state["option_labels"] == ["Mi Gusto (selected)"]

    ledger_entry = store.get_component_ledger(site)["home"]["combo#1"]
    assert ledger_entry["option_labels"] == ["Mi Gusto (selected)"]


def test_record_component_options_defaults_labels_to_empty(store: GraphStore, site: str) -> None:
    store.record_component_options(site, "home", "combo#1", json.dumps({"kind": "unknown"}))

    state = store.get_component_states(site, "home")["combo#1"]
    assert state["option_labels"] == []


def test_record_component_persists_facts(store: GraphStore, site: str) -> None:
    facts = ComponentFacts(
        css_class="btn btn-primary", element_id="go-btn", href="",
        placeholder="", label="Go", name="", disabled=False, required=False, form="",
        color="rgb(255, 255, 255)", background_color="rgb(0, 100, 200)",
        font_size="16px", font_weight="700", display="inline-block", position="static",
    )
    store.record_component(site, "home", "button#go", tag="button", text="Go", facts=facts)

    state = store.get_component_states(site, "home")["button#go"]
    assert state["css_class"] == "btn btn-primary"
    assert state["element_id"] == "go-btn"
    assert state["color"] == "rgb(255, 255, 255)"

    ledger_entry = store.get_component_ledger(site)["home"]["button#go"]
    assert ledger_entry["background_color"] == "rgb(0, 100, 200)"


def test_record_component_defaults_facts_to_blank(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "button#go", tag="button", text="Go")

    state = store.get_component_states(site, "home")["button#go"]
    assert state["css_class"] == ""
    assert state["disabled"] is False
    assert state["color"] == ""


def test_record_component_interaction_auto_creates_node(store: GraphStore, site: str) -> None:
    store.record_component_interaction(site, "home", "button#go", action="click", value="", resulting_url="about")

    states = store.get_component_states(site, "home")
    assert states["button#go"]["interacted"] is True
    # Auto-created ghost node - every ComponentFacts field still defaults blank.
    assert states["button#go"]["css_class"] == ""

    ledger = store.get_component_ledger(site)
    assert ledger["home"]["button#go"]["interactions"] == [
        {
            "action": "click", "value": "", "resulting_url": "about", "source_path": "",
            "visit_id": "", "step_seq": 0,
        }
    ]


def test_repeated_interactions_keep_their_order(store: GraphStore, site: str) -> None:
    for value in ("first", "second", "third"):
        store.record_component_interaction(site, "home", "input#q", action="fill", value=value)

    ledger = store.get_component_ledger(site)
    assert [i["value"] for i in ledger["home"]["input#q"]["interactions"]] == ["first", "second", "third"]


def test_an_interaction_carries_the_position_it_happened_at(store: GraphStore, site: str) -> None:
    step = VisitStep(visit_id="visit-abc")
    store.record_component_interaction(site, "home", "input#q", action="fill", value="x", step=step.take())
    store.record_component_interaction(site, "home", "button#go", action="click", step=step.take())

    ledger = store.get_component_ledger(site)["home"]
    assert ledger["input#q"]["interactions"][0]["visit_id"] == "visit-abc"
    assert ledger["input#q"]["interactions"][0]["step_seq"] == 1
    assert ledger["button#go"]["interactions"][0]["step_seq"] == 2


def test_an_unstamped_interaction_reads_back_as_unordered_not_missing(store: GraphStore, site: str) -> None:
    store.record_component_interaction(site, "home", "button#go", action="click")

    interaction = store.get_component_ledger(site)["home"]["button#go"]["interactions"][0]
    assert interaction["visit_id"] == ""
    assert interaction["step_seq"] == 0


def test_count_unexplored_components_respects_semantic_only(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "button#a", layer="semantic")
    store.record_component(site, "home", "div#b", layer="pointer")

    assert store.count_unexplored_components(site, semantic_only=True) == (1, 1)
    assert store.count_unexplored_components(site, semantic_only=False) == (2, 2)

    store.record_component_interaction(site, "home", "button#a", action="click")
    assert store.count_unexplored_components(site, semantic_only=True) == (0, 1)


def test_page_has_unexplored_components(store: GraphStore, site: str) -> None:
    assert store.page_has_unexplored_components(site, "home") is False

    store.record_component(site, "home", "button#a")
    assert store.page_has_unexplored_components(site, "home") is True

    store.record_component_interaction(site, "home", "button#a", action="click")
    assert store.page_has_unexplored_components(site, "home") is False


def test_get_pages_with_unexplored_components_sorted_descending(store: GraphStore, site: str) -> None:
    store.record_component(site, "x", "button#a")
    store.record_component(site, "y", "button#b")
    store.record_component(site, "y", "button#c")
    store.record_component(site, "z", "button#d")
    store.record_component_interaction(site, "z", "button#d", action="click")

    rows = store.get_pages_with_unexplored_components(site)
    assert rows == [
        {"url": "y", "unexplored_count": 2},
        {"url": "x", "unexplored_count": 1},
    ]


def test_clear_site_removes_components_too(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "button#a")
    store.clear_site(site)

    assert store.get_component_states(site, "home") == {}
    assert store.count_unexplored_components(site) == (0, 0)


def test_component_families_round_trip_and_replace_on_rerun(store: GraphStore, site: str) -> None:
    assert store.get_component_families(site) == []

    families = [
        ComponentFamily(
            tag="button", component_type="submit button",
            common_classes=("btn", "btn-primary"),
            member_paths=((f"{site}/x", "btn1"), (f"{site}/y", "btn2")),
        )
    ]
    store.record_component_families(site, families)
    assert store.get_component_families(site) == families

    # A second, empty write replaces - a stale family must not linger once
    # the underlying data no longer supports it.
    store.record_component_families(site, [])
    assert store.get_component_families(site) == []


def test_component_families_scoped_per_site(store: GraphStore, site: str) -> None:
    other = f"{site}.other"
    family = ComponentFamily(tag="button", component_type="button", common_classes=(), member_paths=((f"{site}/x", "b1"),))
    store.record_component_families(site, [family])

    assert store.get_component_families(site) == [family]
    assert store.get_component_families(other) == []


def test_apply_tag_labels_never_raises_and_leaves_component_readable(store: GraphStore, site: str) -> None:
    """Neo4j gives every tagged Component a real secondary label; a backend
    with no equivalent (in-memory, and any future non-graph backend) treats
    this as a no-op. Both are valid - the only contract is "doesn't raise,
    doesn't lose the component".
    """
    store.record_component(site, "home", "button#a", tag="button")
    store.apply_tag_labels(site, {"button": "Button"})

    assert store.get_component_states(site, "home")["button#a"]["tag"] == "button"


def test_record_component_type_and_options_survive_a_plain_rediscovery(store: GraphStore, site: str) -> None:
    store.record_component(
        site, "home", "div#trigger", tag="div", text="Third Dozen",
        component_type="custom control (component-library element, no native tag/role)",
    )
    options = json.dumps({
        "kind": "combobox_trigger",
        "choices": [{"text": "My Flavor", "selected": True}, {"text": "Plain", "selected": False}],
    })
    store.record_component_options(site, "home", "div#trigger", options)

    states = store.get_component_states(site, "home")
    assert states["div#trigger"]["component_type"] == "custom control (component-library element, no native tag/role)"
    assert json.loads(states["div#trigger"]["options"])["choices"][0]["text"] == "My Flavor"

    # A later plain rediscovery (record_component has no `options` param at
    # all) must not clobber options back to empty - only
    # record_component_options does that. component_type refreshes every
    # call, so it is passed again here.
    store.record_component(
        site, "home", "div#trigger", tag="div", text="Third Dozen (updated)",
        component_type="custom control (component-library element, no native tag/role)",
    )
    states = store.get_component_states(site, "home")
    assert states["div#trigger"]["options"] != ""
    assert states["div#trigger"]["component_type"] != ""


def test_component_family_purpose_round_trips(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component(site, "home", "btn2", tag="button")

    families = [
        ComponentFamily(
            tag="button", component_type="button", common_classes=("btn",),
            member_paths=((f"{site}/home", "btn1"), (f"{site}/home", "btn2")),
            purpose="Confirms or submits an action.",
        )
    ]
    store.record_component_families(site, families)

    assert store.get_component_families(site)[0].purpose == "Confirms or submits an action."


def test_inferred_requests_round_trip_and_replace_on_rerun(store: GraphStore, site: str) -> None:
    assert store.get_inferred_requests(site) == []

    requests = [
        InferredRequest(
            method="POST", endpoint="x.co/rest/v1/orders", query_params=("select",),
            body_shape='{"order_id": "string"}', response_shape='{"id": "string"}',
            triggered_by=((f"{site}/x", "btn1"),),
        )
    ]
    store.record_inferred_requests(site, requests)
    assert store.get_inferred_requests(site) == requests

    store.record_inferred_requests(site, [])
    assert store.get_inferred_requests(site) == []


def test_inferred_request_persists_status_codes_and_load_attribution(store: GraphStore, site: str) -> None:
    store.record_inferred_requests(
        site,
        [InferredRequest(
            method="POST", endpoint="api/orders", query_params=(), body_shape="",
            response_shape="", triggered_by=(), loaded_by=("shop/",),
            status_codes=(201, 422), latencies_ms=(80, 120),
        )],
    )

    read_back = store.get_inferred_requests(site)[0]
    assert read_back.status_codes == (201, 422)
    assert read_back.latencies_ms == (80, 120)
    assert read_back.loaded_by == ("shop/",)


def test_clear_site_removes_families_and_inferred_requests_too(store: GraphStore, site: str) -> None:
    store.record_component(site, "home", "btn1", tag="button")
    store.record_component_families(
        site,
        [ComponentFamily(tag="button", component_type="button", common_classes=(), member_paths=((f"{site}/home", "btn1"),))],
    )
    store.record_inferred_requests(
        site,
        [InferredRequest(
            method="GET", endpoint="x.co/rest/v1/orders", query_params=(),
            body_shape="", response_shape="", triggered_by=((f"{site}/home", "btn1"),),
        )],
    )

    store.clear_site(site)

    assert store.get_component_families(site) == []
    assert store.get_inferred_requests(site) == []


def test_page_metadata_round_trips(store: GraphStore, site: str) -> None:
    store.record_page_metadata(site, "home", json.dumps({"description": "A shop", "og:type": "website"}))

    assert store.get_page_metadata(site) == {"home": {"description": "A shop", "og:type": "website"}}


def test_page_network_ledger_round_trips_and_omits_silent_pages(store: GraphStore, site: str) -> None:
    store.record_page_network(
        site, "orders",
        json.dumps([{"method": "GET", "url": "https://api/x/orders", "status": 200, "latency_ms": 42}]),
    )
    store.upsert_page(site, "static", status="Finished")

    ledger = store.get_page_network_ledger(site)

    assert ledger == {
        "orders": [{"method": "GET", "url": "https://api/x/orders", "status": 200, "latency_ms": 42}]
    }
    assert "static" not in ledger


def test_the_ledger_returns_the_layer_a_filter_depends_on(store: GraphStore, site: str) -> None:
    """`accessibility.undersized_targets` excludes the cursor:pointer
    discovery net by reading `layer` back from the ledger - if a backend
    records it but doesn't return it, that filter silently never fires.
    """
    store.record_component(site, "home", "div#x", tag="div", role="button", input_type="", layer="pointer")

    record = store.get_component_ledger(site)["home"]["div#x"]
    assert record["layer"] == "pointer"
    assert record["role"] == "button"
