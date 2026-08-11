"""Regression tests for Phase 3 of the crawl4ai migration: live GraphStore
writes via MechanicalCrawler + GraphStoreSink (src/crawlers/graph_sink.py).

Uses InMemoryGraphStore (same GraphStore interface Neo4jGraphStore implements)
so these run without a live Neo4j instance - matches the existing test suite's
convention (see tests/test_graph_store.py) of testing the GraphStore contract
against the in-memory backend and leaving live-Neo4j checks to
tests/test_neo4j_graph_store_integration.py, which self-skips when no
instance is reachable.
"""
import asyncio
import http.server
import json
import threading
from pathlib import Path

import pytest

from src.crawlers.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from src.crawlers.graph_sink import GraphStoreInteractionTracker, GraphStoreSink
from src.crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from src.generators.component_classifier import describe_options
from src.storage.memory_graph_store import InMemoryGraphStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"
SITE = "test-site"


@pytest.fixture(scope="module")
def fixture_server():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(FIXTURE_DIR), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()


class _FetchAwareHandler(http.server.SimpleHTTPRequestHandler):
    """Serves fixture files like the plain static handler, but also answers
    `/api/ping` with real JSON - lets `fetch_button.html`'s onclick handler
    hit a real, live endpoint so network-request capture has something
    genuine to see, not just a 404."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FIXTURE_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/ping":
            body = json.dumps({"pong": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # keep test output quiet


@pytest.fixture(scope="module")
def fetch_aware_fixture_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FetchAwareHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()


def _crawl_with_graph_store(start_url: str, **kwargs):
    store = InMemoryGraphStore()
    store.connect()
    sink = GraphStoreSink(store, SITE)

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, **kwargs))
            results = await mech.crawl_site(start_url)
            return mech, results

    results = asyncio.run(run())
    return store, sink, results


def test_page_arrival_and_completion_are_recorded(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    rows = {r["url"]: r for r in store.get_progress_table_rows(SITE)}
    assert any(u.endswith("index.html") for u in rows)
    index_row = next(r for u, r in rows.items() if u.endswith("index.html"))
    assert index_row["status"] == "Finished"
    assert index_row["components"] > 0


def test_page_title_is_persisted(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    titles = store.get_page_titles(SITE)
    assert titles.get(page_key) == "Mechanical loop fixture: index"


def test_component_inventory_is_recorded_unconditionally(fixture_server):
    """Every discovered component gets a Component node, including ones the
    interaction budget never got around to touching."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/chain.html", max_pages=1, element_budget=1)
    page_key = results[0].url
    states = store.get_component_states(SITE, page_key)
    # chain.html's c0 is the only initially-visible button (c1-c4 start
    # CSS-hidden) - it must be in the inventory regardless of whether the
    # tight element_budget got around to interacting with it.
    assert any("c0" in path for path in states)


def test_interaction_ledger_records_attempted_actions(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    ledger = store.get_component_ledger(SITE)
    page_ledger = ledger.get(page_key, {})
    fill_entries = [
        c for c in page_ledger.values()
        if c.get("interacted") and any(i["action"] == "fill" for i in c.get("interactions", []))
    ]
    assert fill_entries, "the fillable nameInput field must show up as interacted in the persisted ledger"


def test_navigation_produces_a_graph_edge(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    edges = store.get_edges(SITE)
    to_page_b = [e for e in edges if e["to"].endswith("page-b.html")]
    assert to_page_b, "a navigating click/link must produce a recorded edge into page-b.html"


def test_graph_backed_tracker_prevents_re_interaction_across_a_fresh_mechanical_crawler(fixture_server):
    """The whole point of Phase 3: a second MechanicalCrawler instance,
    sharing the same GraphStore, must not redo work the first one already
    did - the persisted ledger is what makes this possible without any
    in-process state carried over."""
    store = InMemoryGraphStore()
    store.connect()
    sink = GraphStoreSink(store, SITE)

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech1 = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, max_pages=15))
            await mech1.crawl_site(f"{fixture_server}/index.html")
            mech2 = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, max_pages=15))
            return await mech2.crawl_site(f"{fixture_server}/index.html")

    results = asyncio.run(run())
    index_results = [r for r in results if r.url.endswith("index.html")]
    total_interactions = sum(len(r.interactions) for r in index_results)
    assert total_interactions == 0


def test_default_tracker_derives_from_sink_when_no_explicit_tracker_given(fixture_server):
    store = InMemoryGraphStore()
    store.connect()
    sink = GraphStoreSink(store, SITE)

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, max_pages=1))
            assert isinstance(mech.tracker, GraphStoreInteractionTracker)
            return mech.tracker

    tracker = asyncio.run(run())
    assert tracker.graph_store is store
    assert tracker.site == SITE


def test_revealed_dropdown_options_consolidate_into_one_real_node(fixture_server):
    """Supersedes the narrower 2026-08-08 ghost-node fix (which this test used
    to guard as 3 separate Small/Medium/Large nodes, one per option): a
    revealed dropdown's options are now group_option_families'd into ONE
    consolidated Component node, not N near-identical ones differing only by
    which option they are - see component_classifier.group_option_families
    and GraphStoreSink._record_choice_group. The original ghost-node failure
    mode (a blank auto-created stub instead of real fields) is still guarded
    against: it must be that one real node, not a blank one."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/reveal.html", max_pages=1, page_concurrency=1)
    page_key = results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]

    option_entries = {c["text"]: c for c in ledger.values() if c.get("text") in ("Small", "Medium", "Large")}
    assert set(option_entries) == {"Small"}, "the 3 revealed options must collapse into 1 representative node"
    entry = option_entries["Small"]
    assert entry["tag"] == "div", "the representative must carry real fields, not a ghost-node blank"
    assert entry["component_type"], "the representative must have a real component_type"

    parsed = describe_options(entry["options"])
    assert parsed["kind"] == "choice_group"
    assert {c["text"] for c in parsed["choices"]} == {"Small", "Medium", "Large"}

    # A link that only exists inside the revealed popover must also get
    # queued - regression for the _enqueue_links gap in the same branch.
    rows = {r["url"]: r for r in store.get_progress_table_rows(SITE)}
    assert any(u.endswith("size-details") for u in rows), "a link revealed only via a popover must still be queued"


def test_stepper_detected_in_a_revealed_snapshot_not_just_the_initial_one(fixture_server):
    """Falls out of the same record_inventory fix for free (per the plan):
    group_steppers already runs inside record_inventory over whatever
    component list it's given, so a stepper that only appears after a reveal
    (reveal.html's quantity control) must get its options field populated
    once record_inventory is called again for that reveal's snapshot."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/reveal.html", max_pages=1, page_concurrency=1)
    page_key = results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]

    minus_entry = next((c for path, c in ledger.items() if "qtyMinus" in path), None)
    assert minus_entry is not None, "the revealed stepper's decrement button must be inventoried"
    assert minus_entry["tag"] == "button", "must have real descriptive fields, not a ghost-node blank"

    # record_inventory attaches the stepper's options JSON to the increment
    # path only (see GraphStoreSink.record_inventory), not both members.
    plus_entry = next((c for path, c in ledger.items() if "qtyPlus" in path), None)
    assert plus_entry is not None
    assert plus_entry["options"], "the stepper's options field must be populated on the increment path"


def test_revealed_options_attributed_to_trigger_component(fixture_server):
    """Phase 1: the trigger's own `options` field must carry the diff-
    detected revealed options, keyed the way GraphStoreSink.record_revealed_options
    writes them."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/reveal.html", max_pages=1, page_concurrency=1)
    page_key = results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]

    trigger_entry = next((c for path, c in ledger.items() if "sizeTrigger" in path), None)
    assert trigger_entry is not None
    options = json.loads(trigger_entry["options"])
    assert options["trigger"].endswith("sizeTrigger")
    revealed_texts = {o["text"] for o in options["revealed_options"]}
    assert revealed_texts == {"Small", "Medium", "Large"}


def test_fetch_triggered_by_click_is_captured_and_attributed(fetch_aware_fixture_server):
    """Phase 3: a click that fires a real fetch() must show up on the
    clicked component's own network_requests, with a real joined status -
    the case a static <form method/action> reading would see nothing on."""
    store, sink, (mech, results) = _crawl_with_graph_store(
        f"{fetch_aware_fixture_server}/fetch_button.html", max_pages=1
    )
    page_key = results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]
    button_entry = next((c for path, c in ledger.items() if "pingButton" in path), None)
    assert button_entry is not None
    requests = button_entry["network_requests"]
    assert requests, "the click must have captured at least one meaningful request"
    ping = next(r for r in requests if r["url"].endswith("/api/ping"))
    assert ping["resource_type"] == "fetch"
    assert ping["status"] == 200
    assert ping["failed"] is False


def test_static_form_produces_no_network_requests(fixture_server):
    """Contrast case: a plain HTML form submit fires no XHR/fetch at all -
    network_requests must stay empty, not be fabricated from the form's own
    static method/action attributes."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/form.html", max_pages=1)
    page_key = results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]
    submit_entry = next((c for path, c in ledger.items() if c.get("tag") == "button"), None)
    assert submit_entry is not None
    assert submit_entry["network_requests"] == []


def test_static_text_content_captured_as_distinct_kind(fixture_server):
    """Phase 4: non-interactive prose gets its own TextContent record kind,
    separate from Component - and a <p> nested inside a button is excluded
    (it's that button's own accessible label, already captured there)."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    text_ledger = store.get_text_content_ledger(SITE).get(page_key, [])
    texts = {e["text"] for e in text_ledger}

    assert "Index" in texts
    assert "A paragraph of real page text, not an interactive component." in texts
    assert "First list item text" in texts
    assert "Label wrapped in a paragraph" not in texts, (
        "a <p> nested inside a button is that button's own label, not a separate text leaf"
    )

    heading = next(e for e in text_ledger if e["text"] == "Index")
    assert heading["tag"] == "h1"


def test_budget_exhausted_page_gets_fully_drained_within_its_round_ceiling(fixture_server):
    """Regression test for the exhaustive-coverage bug (2026-08-08): a page
    with more components than element_budget must get ALL of them
    interacted with, not just however many fit in the first element_budget's
    worth - handled internally as extra "rounds" within one continuous
    session (element_budget * max_passes_per_page is the real ceiling), not
    by re-navigating (which would reset same-page reveal state - see
    crawl_site's docstring). Not marked Finished until genuinely drained."""
    store, sink, (mech, results) = _crawl_with_graph_store(
        f"{fixture_server}/chain.html", max_pages=15, element_budget=2
    )
    chain_results = [r for r in results if r.url.endswith("chain.html")]
    assert len(chain_results) == 1, "budget exhaustion is handled internally - still one _visit_page call"
    assert chain_results[0].budget_exhausted_with_frontier_remaining is False, "must have fully drained"

    page_key = chain_results[0].url
    ledger = store.get_component_ledger(SITE)[page_key]
    all_interacted = [c for path, c in ledger.items() if path.split("#")[-1].startswith("c") and c["tag"] == "button"]
    assert all(c["interacted"] for c in all_interacted), "every chain button must eventually be interacted with"
    assert len(all_interacted) == 5, "all 5 chain buttons must have been discovered and inventoried"

    rows = {r["url"]: r for r in store.get_progress_table_rows(SITE)}
    assert rows[page_key]["status"] == "Finished", "must be marked Finished once genuinely fully drained"


def test_page_exceeding_max_passes_per_page_is_abandoned_gracefully_not_marked_finished(fixture_server):
    """A page that keeps generating genuinely new content faster than the
    round ceiling can keep up with (infinite_reveal.html) must be abandoned
    after element_budget * max_passes_per_page interactions, not looped
    forever - and must NOT be falsely marked Finished, since it never was."""
    store, sink, (mech, results) = _crawl_with_graph_store(
        f"{fixture_server}/infinite_reveal.html",
        max_pages=50, element_budget=1, max_passes_per_page=3,
    )
    infinite_results = [r for r in results if r.url.endswith("infinite_reveal.html")]
    assert len(infinite_results) == 1, "still one _visit_page call - the round ceiling is internal"
    assert infinite_results[0].budget_exhausted_with_frontier_remaining is True
    assert len(infinite_results[0].interactions) == 3, "must stop after exactly element_budget * max_passes_per_page"

    page_key = infinite_results[0].url
    rows = {r["url"]: r for r in store.get_progress_table_rows(SITE)}
    assert rows[page_key]["status"] != "Finished", "an abandoned page must never be falsely marked Finished"
