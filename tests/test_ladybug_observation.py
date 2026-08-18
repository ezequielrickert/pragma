"""Regression tests for the observation-tier write path -
`database/ladybug/page.py`/`component.py`/`text_content.py` (storage-
migration plan step 4), exercised through `LadybugGraphStore`'s public
API rather than per-mixin, since that's the contract that matters. Two of
these (`test_record_components_batch_...`, `test_record_text_contents_batch_...`)
pin a real engine bug found while building this: an `UNWIND` batch whose
geometry fields are uniformly `None` across every row makes Ladybug infer
that column as `STRING` instead of `DOUBLE` and reject the write - see
`_cypher.py::_DOUBLE_FIELDS`'s own comment for the fix.
"""
from __future__ import annotations

import pytest

from core.interfaces import ComponentFacts, VisitStep
from database.ladybug.store import LadybugGraphStore


@pytest.fixture
def store():
    instance = LadybugGraphStore("test.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _rows(store: LadybugGraphStore, query: str, **params):
    return list(store._call(lambda conn: list(conn.execute(query, params))))


def test_upsert_page_pending_never_clobbers_finished(store) -> None:
    store.upsert_page("https://x/y", status="Pending")
    store.upsert_page("https://x/y", status="Finished", components=5, title="Home")
    store.upsert_page("https://x/y", status="Pending")

    row = _rows(store, "MATCH (p:Page {url: $url}) RETURN p.status, p.component_count", url="https://x/y")
    assert row == [["Finished", 5]]


def test_upsert_page_sets_caption_from_title_or_falls_back_to_url(store) -> None:
    store.upsert_page("https://x/y", status="Finished", title="Home")
    store.upsert_page("https://x/z", status="Finished")

    with_title = _rows(store, "MATCH (p:Page {url: $url}) RETURN p.caption", url="https://x/y")
    without_title = _rows(store, "MATCH (p:Page {url: $url}) RETURN p.caption", url="https://x/z")
    assert with_title == [["Home"]]
    assert without_title == [["https://x/z"]]


def test_record_page_metadata_stores_a_map(store) -> None:
    store.record_page_metadata("https://x/y", {"viewport": "width=device-width", "og:title": "Home"})

    row = _rows(store, "MATCH (p:Page {url: $url}) RETURN p.metadata", url="https://x/y")
    assert row == [[{"viewport": "width=device-width", "og:title": "Home"}]]


def test_record_text_content_creates_node_and_edge(store) -> None:
    store.record_text_content("https://x/y", "p.intro", tag="p", text="Welcome")

    row = _rows(
        store,
        "MATCH (p:Page {url: $url})-[:HAS_TEXT]->(t:TextContent) RETURN t.path, t.tag, t.text",
        url="https://x/y",
    )
    assert row == [["p.intro", "p", "Welcome"]]


def test_record_text_contents_batch_with_all_none_geometry(store) -> None:
    """Pins the STRUCT_EXTRACT/DOUBLE bug - every entry below omits
    x/y/width/height entirely."""
    store.record_text_contents(
        "https://x/y",
        [{"path": "h1", "tag": "h1", "text": "Title"}, {"path": "span.x", "tag": "span", "text": "x", "visible": False}],
    )

    rows = _rows(
        store,
        "MATCH (:Page {url: $url})-[:HAS_TEXT]->(t:TextContent) RETURN t.path, t.visible, t.x ORDER BY t.path",
        url="https://x/y",
    )
    assert rows == [["h1", True, None], ["span.x", False, None]]


def test_record_links_batch_overwrites_label_on_rediscovery(store) -> None:
    store.record_link("https://x/y", "https://x/about", "About Us")
    store.record_links("https://x/y", [{"to_url": "https://x/about", "label": "About (updated)"}])

    row = _rows(
        store,
        "MATCH (:Page {url: $from})-[l:LINKS_TO]->(:Page {url: $to}) RETURN l.label",
        **{"from": "https://x/y", "to": "https://x/about"},
    )
    assert row == [["About (updated)"]]


def test_record_edge_dedups_and_tracks_run_provenance(store) -> None:
    store.record_edge("https://x/y", "https://x/cart", "button#go", "click", run_id="run-1")
    store.record_edge("https://x/y", "https://x/cart", "button#go", "click", run_id="run-2")

    row = _rows(store, "MATCH ()-[e:NAVIGATES_TO]->() RETURN e.observation_count, e.first_seen_run, e.last_seen_run")
    assert row == [[2, "run-1", "run-2"]]


def test_record_component_rediscovery_updates_descriptive_fields_only(store) -> None:
    store.record_component("https://x/y", "button#go", tag="button", text="Go",
                            facts=ComponentFacts(css_class="btn"))
    store._call(lambda conn: conn.execute(
        "MATCH (c:Component {id: $id}) SET c.interacted = true, c.interaction_count = 3",
        {"id": "https://x/y|button#go"},
    ))

    store.record_component("https://x/y", "button#go", tag="button", text="Go (rediscovered)")

    row = _rows(store, "MATCH (c:Component {id: $id}) RETURN c.text, c.interacted, c.interaction_count",
                id="https://x/y|button#go")
    assert row == [["Go (rediscovered)", True, 3]]


def test_record_component_persists_position(store) -> None:
    store.record_component("https://x/y", "div#box", x=12.5, y=34.0, width=100.0, height=50.0)

    row = _rows(store, "MATCH (c:Component {id: $id}) RETURN c.x, c.y, c.width, c.height",
                id="https://x/y|div#box")
    assert row == [[12.5, 34.0, 100.0, 50.0]]


def test_record_component_defaults_facts_to_blank_when_none_given(store) -> None:
    store.record_component("https://x/y", "div#box")

    row = _rows(store, "MATCH (c:Component {id: $id}) RETURN c.css_class, c.required",
                id="https://x/y|div#box")
    assert row == [["", False]]


def test_record_components_batch_with_mixed_and_all_none_geometry(store) -> None:
    """Pins the same STRUCT_EXTRACT/DOUBLE bug as the TextContent case,
    for the field a real page is far more likely to trip it on."""
    store.record_components(
        "https://x/y",
        [
            {"path": "input#email", "tag": "input", "input_type": "email"},
            {"path": "a#skip", "tag": "a", "text": "Skip", "x": 10.0, "y": 20.0},
        ],
    )

    rows = _rows(
        store,
        "MATCH (:Page {url: $url})-[:HAS_COMPONENT]->(c:Component) RETURN c.path, c.x, c.y ORDER BY c.path",
        url="https://x/y",
    )
    assert rows == [["a#skip", 10.0, 20.0], ["input#email", None, None]]


def test_record_component_interaction_creates_the_full_chain(store) -> None:
    store.record_component("https://x/y", "button#go", tag="button")
    step = VisitStep(visit_id="v1").take()

    store.record_component_interaction(
        "https://x/y", "button#go", "click", resulting_url="https://x/cart", step=step,
    )

    row = _rows(
        store,
        """
        MATCH (c:Component {id: $id})-[:PERFORMED]->(i:Interaction)-[:RESULTED_IN]->(target:Page)
        RETURN c.interacted, c.interaction_count, i.action, i.visit_id, i.step_seq, target.url
        """,
        id="https://x/y|button#go",
    )
    # "x/cart", not the literal "https://x/cart" passed in - resulting_url
    # is route_shape'd before it names a page, same as every other page
    # identity that reaches storage (see record_component_interaction's
    # own docstring for why this one write path has to enforce it itself).
    assert row == [[True, 1, "click", "v1", 1, "x/cart"]]


def test_record_component_interaction_with_no_navigation_points_back_at_own_page(store) -> None:
    store.record_component("https://x/y", "select#opt", tag="select")

    store.record_component_interaction("https://x/y", "select#opt", "click")

    row = _rows(
        store,
        "MATCH (:Component {id: $id})-[:PERFORMED]->(:Interaction)-[:RESULTED_IN]->(target:Page) RETURN target.url",
        id="https://x/y|select#opt",
    )
    assert row == [["https://x/y"]]


def test_get_component_states_reports_interacted_flag_per_path(store) -> None:
    store.record_components("https://x/y", [{"path": "a#skip"}, {"path": "button#go"}])
    store.record_component_interaction("https://x/y", "button#go", "click")

    states = store.get_component_states("https://x/y")

    assert set(states.keys()) == {"a#skip", "button#go"}
    assert states["a#skip"]["interacted"] is False
    assert states["button#go"]["interacted"] is True


def test_get_component_states_is_scoped_to_the_requested_page(store) -> None:
    store.record_component("https://x/y", "a#skip")
    store.record_component("https://x/other", "a#skip")

    states = store.get_component_states("https://x/y")

    assert list(states.keys()) == ["a#skip"]


def test_is_visited_true_only_for_finished_or_failed(store) -> None:
    store.upsert_page("https://x/done", status="Finished")
    store.upsert_page("https://x/failed", status="Failed")
    store.upsert_page("https://x/pending", status="Pending")

    assert store.is_visited("https://x/done") is True
    assert store.is_visited("https://x/failed") is True
    assert store.is_visited("https://x/pending") is False


def test_is_visited_false_for_an_unknown_url(store) -> None:
    assert store.is_visited("https://x/never-seen") is False


def test_ensure_page_creates_a_pending_stub_referenced_by_a_link(store) -> None:
    store.record_link("https://x/y", "https://x/undiscovered", "Later")

    row = _rows(store, "MATCH (p:Page {url: $url}) RETURN p.status", url="https://x/undiscovered")
    assert row == [["Pending"]]
