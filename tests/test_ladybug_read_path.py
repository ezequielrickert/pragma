"""Regression tests for the read path added in storage-migration plan
step 5 - `get_pending`, `get_progress_table_rows`, `get_page_descriptions`/
`get_page_titles`, `count_visited`, `get_edges`, `count_unexplored_components`,
`get_component_ledger`, `get_text_content_ledger`,
`record_component_families`/`get_component_families`, and
`record_page_metrics`/`record_page_modules` (`database/ladybug/page.py`,
`component.py`, `text_content.py`, `component_family.py`, `analysis.py`).

`test_count_visited_return_value_is_json_serializable` and
`test_record_page_metrics_batch_with_all_none_click_depth` each pin a
real engine bug found while building this - see their own docstrings.
"""
from __future__ import annotations

import json

import pytest

from core.interfaces import ComponentFamily, VisitStep
from database.ladybug.store import LadybugGraphStore


@pytest.fixture
def store():
    instance = LadybugGraphStore("test.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def test_get_pending_returns_only_pending_urls_sorted(store) -> None:
    store.upsert_page("https://x/b", status="Pending")
    store.upsert_page("https://x/a", status="Pending")
    store.upsert_page("https://x/done", status="Finished")

    assert store.get_pending() == ["https://x/a", "https://x/b"]


def test_get_pending_respects_limit(store) -> None:
    store.upsert_page("https://x/a", status="Pending")
    store.upsert_page("https://x/b", status="Pending")

    assert store.get_pending(limit=1) == ["https://x/a"]


def test_get_progress_table_rows_orders_unfinished_first_then_by_url(store) -> None:
    store.upsert_page("https://x/z", status="Finished", components=3)
    store.upsert_page("https://x/a", status="Pending")

    rows = store.get_progress_table_rows()

    assert rows == [
        {"url": "https://x/a", "status": "Pending", "components": 0},
        {"url": "https://x/z", "status": "Finished", "components": 3},
    ]


def test_get_page_descriptions_and_titles_omit_pages_without_one(store) -> None:
    store.upsert_page("https://x/a", status="Finished", title="Home", description="desc")
    store.upsert_page("https://x/b", status="Finished")

    assert store.get_page_descriptions() == {"https://x/a": "desc"}
    assert store.get_page_titles() == {"https://x/a": "Home"}


def test_count_visited_excludes_external_pages(store) -> None:
    store.upsert_page("https://x/done", status="Finished")
    store.upsert_page("https://x/pending", status="Pending")
    store.upsert_page("https://x/off-site", status="External")

    assert store.count_visited() == (1, 2)


def test_count_visited_return_value_is_json_serializable(store) -> None:
    """`sum(CASE WHEN ...)` comes back as `decimal.Decimal` from the real
    engine, not `int` - `count_visited`'s result feeds
    `utils.io.record_run_manifest`'s `json.dumps` directly, which raises
    on a bare Decimal."""
    store.upsert_page("https://x/done", status="Finished")

    finished, total = store.count_visited()

    json.dumps({"finished": finished, "total": total})  # must not raise


def test_get_edges_reports_observation_count_and_run_provenance(store) -> None:
    store.record_edge("https://x/a", "https://x/b", "button#go", "click", run_id="run-1")
    store.record_edge("https://x/a", "https://x/b", "button#go", "click", run_id="run-2")

    edges = store.get_edges()

    assert edges == [
        {
            "from": "https://x/a", "component": "button#go", "action": "click", "to": "https://x/b",
            "observation_count": 2, "first_seen_run": "run-1", "last_seen_run": "run-2",
        }
    ]


def test_count_unexplored_components_counts_interacted_vs_total(store) -> None:
    store.record_component("https://x/a", "button#go")
    store.record_component("https://x/a", "a#skip")
    store.record_component_interaction("https://x/a", "button#go", "click")

    assert store.count_unexplored_components() == (1, 2)


def test_count_unexplored_components_semantic_only_excludes_pointer_layer(store) -> None:
    store.record_component("https://x/a", "div#clickable", layer="pointer")
    store.record_component("https://x/a", "button#go", layer="semantic")

    assert store.count_unexplored_components(semantic_only=True) == (1, 1)
    assert store.count_unexplored_components(semantic_only=False) == (2, 2)


def test_get_component_ledger_nests_by_page_then_path_with_interactions(store) -> None:
    store.record_component("https://x/a", "button#go", text="Go")
    step = VisitStep(visit_id="v1").take()
    store.record_component_interaction("https://x/a", "button#go", "click", resulting_url="https://x/b", step=step)

    ledger = store.get_component_ledger()

    record = ledger["https://x/a"]["button#go"]
    assert record["text"] == "Go"
    assert record["interacted"] is True
    # "x/b", not the literal "https://x/b" passed in - resulting_url is
    # route_shape'd before it names a page (record_component_interaction's
    # own docstring explains why this one write path enforces it itself).
    assert record["interactions"] == [
        {"action": "click", "value": "", "resulting_url": "x/b",
         "source_path": "", "visit_id": "v1", "step_seq": 1}
    ]


def test_get_component_ledger_repeated_interactions_keep_their_order(store) -> None:
    """Ordering has no manual counter behind it anymore - SERIAL's own
    insertion order under the single writer is what `ORDER BY i.id`
    relies on, replacing the retired DuckDB backend's `RETURNING
    interaction_count`-based `seq`."""
    store.record_component("https://x/a", "input#q")
    for value in ("first", "second", "third"):
        store.record_component_interaction("https://x/a", "input#q", "fill", value=value)

    interactions = store.get_component_ledger()["https://x/a"]["input#q"]["interactions"]

    assert [i["value"] for i in interactions] == ["first", "second", "third"]


def test_get_component_ledger_step_seq_orders_across_components_in_one_visit(store) -> None:
    store.record_component("https://x/a", "input#q")
    store.record_component("https://x/a", "button#go")
    step = VisitStep(visit_id="visit-abc")
    store.record_component_interaction("https://x/a", "input#q", "fill", value="x", step=step.take())
    store.record_component_interaction("https://x/a", "button#go", "click", step=step.take())

    ledger = store.get_component_ledger()["https://x/a"]

    assert ledger["input#q"]["interactions"][0]["visit_id"] == "visit-abc"
    assert ledger["input#q"]["interactions"][0]["step_seq"] == 1
    assert ledger["button#go"]["interactions"][0]["step_seq"] == 2


def test_get_component_ledger_unstamped_interaction_reads_back_as_unordered_not_missing(store) -> None:
    store.record_component("https://x/a", "button#go")
    store.record_component_interaction("https://x/a", "button#go", "click")

    interaction = store.get_component_ledger()["https://x/a"]["button#go"]["interactions"][0]

    assert interaction["visit_id"] == ""
    assert interaction["step_seq"] == 0


def test_get_component_ledger_reports_the_layer_a_downstream_filter_depends_on(store) -> None:
    store.record_component("https://x/a", "div#x", role="button", input_type="", layer="pointer")

    record = store.get_component_ledger()["https://x/a"]["div#x"]

    assert record["layer"] == "pointer"
    assert record["role"] == "button"


def test_get_text_content_ledger_groups_by_page(store) -> None:
    store.record_text_content("https://x/a", "p.intro", tag="p", text="Welcome")
    store.record_text_content("https://x/b", "h1", tag="h1", text="Title")

    ledger = store.get_text_content_ledger()

    assert sorted(ledger.keys()) == ["https://x/a", "https://x/b"]
    assert ledger["https://x/a"][0]["text"] == "Welcome"


def test_component_families_round_trip_and_skip_unresolvable_members(store) -> None:
    store.record_component("https://x/a", "button#go")

    families = [
        ComponentFamily(
            tag="button", component_type="button", common_classes=("btn",),
            member_paths=(("https://x/a", "button#go"), ("https://x/a", "missing#nope")),
            purpose="Confirms an action",
        )
    ]
    store.record_component_families(families)

    got = store.get_component_families()

    assert len(got) == 1
    assert got[0].member_paths == (("https://x/a", "button#go"),)
    assert got[0].purpose == "Confirms an action"


def test_component_families_two_families_with_identical_properties_stay_distinct(store) -> None:
    """Grouping happens on the node itself, not a Python-side key derived
    from its properties - `id(f)` comes back as an unhashable dict from
    the real engine, and even if it didn't, two families sharing every
    property would be a real (if unlikely) case this must not collapse."""
    store.record_component("https://x/a", "button#go")
    store.record_component("https://x/b", "button#submit")

    families = [
        ComponentFamily(tag="button", component_type="button", common_classes=(),
                         member_paths=(("https://x/a", "button#go"),), purpose=""),
        ComponentFamily(tag="button", component_type="button", common_classes=(),
                         member_paths=(("https://x/b", "button#submit"),), purpose=""),
    ]
    store.record_component_families(families)

    got = store.get_component_families()

    assert len(got) == 2
    assert {f.member_paths for f in got} == {
        (("https://x/a", "button#go"),), (("https://x/b", "button#submit"),),
    }


def test_record_component_families_is_a_full_rebuild(store) -> None:
    store.record_component("https://x/a", "button#go")
    store.record_component_families(
        [ComponentFamily(tag="button", component_type="button", common_classes=(),
                          member_paths=(("https://x/a", "button#go"),), purpose="")]
    )

    store.record_component_families([])

    assert store.get_component_families() == []


def test_record_page_metrics_writes_page_properties(store) -> None:
    store.upsert_page("https://x/a", status="Finished")

    store.record_page_metrics([
        {"url": "https://x/a", "in_degree": 1, "out_degree": 2, "click_depth": 0,
         "betweenness": 0.5, "pagerank": 0.3, "is_articulation_point": True},
    ])

    row = store._call(lambda conn: list(conn.execute(
        "MATCH (p:Page {url: $url}) RETURN p.in_degree, p.out_degree, p.click_depth, "
        "p.betweenness, p.pagerank, p.is_articulation_point",
        {"url": "https://x/a"},
    )))
    assert row == [[1, 2, 0, 0.5, 0.3, True]]


def test_record_page_metrics_batch_with_all_none_click_depth(store) -> None:
    """Pins the same STRUCT_EXTRACT/type-inference bug the observation
    write path hit, here for an INT64 column rather than DOUBLE - a
    disconnected page's click_depth is None, and an entire batch of them
    reproduces it just as reliably as an all-None geometry field does."""
    store.upsert_page("https://x/unreachable", status="Finished")

    store.record_page_metrics([
        {"url": "https://x/unreachable", "in_degree": 0, "out_degree": 0, "click_depth": None,
         "betweenness": 0.0, "pagerank": 0.0, "is_articulation_point": False},
    ])

    row = store._call(lambda conn: list(conn.execute(
        "MATCH (p:Page {url: $url}) RETURN p.click_depth", {"url": "https://x/unreachable"},
    )))
    assert row == [[None]]


def test_record_page_modules_writes_page_properties(store) -> None:
    store.upsert_page("https://x/a", status="Finished")

    store.record_page_modules([{"url": "https://x/a", "module_id": 2, "module_label": "Shop"}])

    row = store._call(lambda conn: list(conn.execute(
        "MATCH (p:Page {url: $url}) RETURN p.module_id, p.module_label", {"url": "https://x/a"},
    )))
    assert row == [[2, "Shop"]]
