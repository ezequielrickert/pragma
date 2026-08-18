"""Regression tests for Phase 3 of the crawl4ai migration: live GraphStore
writes via MechanicalCrawler + GraphStoreSink (spiders/orchestration/graph_sink.py).

Uses LadybugGraphStore in-memory mode so these run with no setup at all -
matches the existing test suite's convention (see tests/test_graph_store.py).
The store's own contract is covered by tests/test_ladybug_observation.py/
test_ladybug_read_path.py.

Option/Request write paths (storage-migration plan steps 7-8) are both
real now. Fetch-request attribution is covered end-to-end below; Option
membership is covered end-to-end by tests/test_component_tree.py and at
the storage layer by tests/test_ladybug_options.py, not duplicated here.
"""
import asyncio
import http.server
import json
import threading
from pathlib import Path

import pytest

from generators.component_classifier import describe_options_from_rows
from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.orchestration.graph_sink import GraphStoreInteractionTracker, GraphStoreSink
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from database.ladybug.store import LadybugGraphStore

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
    store = LadybugGraphStore(SITE)
    store.connect()
    sink = GraphStoreSink(store)

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, **kwargs))
            results = await mech.crawl_site(start_url)
            return mech, results

    results = asyncio.run(run())
    return store, sink, results


def test_page_arrival_and_completion_are_recorded(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    rows = {r["url"]: r for r in store.get_progress_table_rows()}
    assert any(u.endswith("index.html") for u in rows)
    index_row = next(r for u, r in rows.items() if u.endswith("index.html"))
    assert index_row["status"] == "Finished"
    assert index_row["components"] > 0


def test_page_title_is_persisted(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    titles = store.get_page_titles()
    assert titles.get(page_key) == "Mechanical loop fixture: index"


def test_component_inventory_is_recorded_unconditionally(fixture_server):
    """Every discovered component gets a Component node purely from
    discovery, before any interaction happens - `record_inventory` runs
    right after `discover_page`, independent of the interaction loop."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/chain.html", max_pages=1)
    page_key = results[0].url
    states = store.get_component_states(page_key)
    # chain.html's c0 is the only initially-visible button (c1-c4 start
    # CSS-hidden) - it must be in the inventory from the very first
    # discovery, before this pass ever clicks anything.
    assert any("c0" in path for path in states)


def test_interaction_ledger_records_attempted_actions(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    ledger = store.get_component_ledger()
    page_ledger = ledger.get(page_key, {})
    fill_entries = [
        c for c in page_ledger.values()
        if c.get("interacted") and any(i["action"] == "fill" for i in c.get("interactions", []))
    ]
    assert fill_entries, "the fillable nameInput field must show up as interacted in the persisted ledger"


def test_clicking_a_fetch_button_records_a_request_attributed_to_the_click(fetch_aware_fixture_server):
    """End-to-end: a real click fires a real `fetch('/api/ping')`, and the
    resulting `Request` node ends up hung off exactly that click's own
    `Interaction` (`TRIGGERED`), not floating unattributed - the capability
    `fetch_aware_fixture_server`/`fetch_button.html` exist to exercise,
    dormant until storage-migration plan step 7 landed."""
    store, sink, (mech, results) = _crawl_with_graph_store(
        f"{fetch_aware_fixture_server}/fetch_button.html", max_pages=1
    )
    page_key = results[0].url

    ledger = store.get_component_ledger()
    button = next(c for c in ledger[page_key].values() if c.get("element_id") == "pingButton")
    assert button["network_requests"], "the click must have an attributed request, not an empty pool"
    request = button["network_requests"][0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/ping"
    assert request["status"] == 200

    inferred = store.get_inferred_requests()
    assert any(r.endpoint.endswith("/api/ping") for r in inferred)


def test_navigation_produces_a_graph_edge(fixture_server):
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    edges = store.get_edges()
    to_page_b = [e for e in edges if e["to"].endswith("page-b.html")]
    assert to_page_b, "a navigating click/link must produce a recorded edge into page-b.html"


def test_graph_backed_tracker_prevents_re_interaction_across_a_fresh_mechanical_crawler(fixture_server):
    """The whole point of Phase 3: a second MechanicalCrawler instance,
    sharing the same GraphStore, must not redo work the first one already
    did - the persisted ledger is what makes this possible without any
    in-process state carried over."""
    store = LadybugGraphStore(SITE)
    store.connect()
    sink = GraphStoreSink(store)

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
    store = LadybugGraphStore(SITE)
    store.connect()
    sink = GraphStoreSink(store)

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, max_pages=1))
            assert isinstance(mech.tracker, GraphStoreInteractionTracker)
            return mech.tracker

    tracker = asyncio.run(run())
    assert tracker.graph_store is store


def test_revealed_dropdown_options_consolidate_into_one_real_node(fixture_server):
    """Supersedes the narrower 2026-08-08 ghost-node fix (which this test used
    to guard as 3 separate Small/Medium/Large nodes, one per option): a
    revealed dropdown's options are now group_option_families'd into ONE
    consolidated Component node, not N near-identical ones differing only by
    which option they are - see component_classifier.group_option_families
    and GraphStoreSink._record_choice_group. The original ghost-node failure
    mode (a blank auto-created stub instead of real fields) is still guarded
    against: it must be that one real node, not a blank one.

    The `options` field itself (what choices the consolidated node
    offers) is checked too: the representative's own `Option` rows must
    list all three revealed choices, not just the one whose text
    happened to survive consolidation onto the Component node."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/reveal.html", max_pages=1, page_concurrency=1)
    page_key = results[0].url
    ledger = store.get_component_ledger()[page_key]

    option_entries = {c["text"]: c for c in ledger.values() if c.get("text") in ("Small", "Medium", "Large")}
    assert set(option_entries) == {"Small"}, "the 3 revealed options must collapse into 1 representative node"
    entry = option_entries["Small"]
    assert entry["tag"] == "div", "the representative must carry real fields, not a ghost-node blank"
    assert entry["component_type"], "the representative must have a real component_type"

    parsed = describe_options_from_rows(*entry["options"])
    assert parsed is not None, "the consolidated node must carry the choices it represents"
    choice_texts = {c["text"] for c in parsed["choices"]}
    assert choice_texts == {"Small", "Medium", "Large"}

    # A link that only exists inside the revealed popover must also get
    # queued - regression for the _enqueue_links gap in the same branch.
    rows = {r["url"]: r for r in store.get_progress_table_rows()}
    assert any(u.endswith("size-details") for u in rows), "a link revealed only via a popover must still be queued"


def test_stepper_detected_in_a_revealed_snapshot_not_just_the_initial_one(fixture_server):
    """Falls out of the same record_inventory fix for free (per the plan):
    group_steppers already runs inside record_inventory over whatever
    component list it's given, so a stepper that only appears after a reveal
    (reveal.html's quantity control) must get inventoried once
    record_inventory is called again for that reveal's snapshot."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/reveal.html", max_pages=1, page_concurrency=1)
    page_key = results[0].url
    ledger = store.get_component_ledger()[page_key]

    minus_entry = next((c for path, c in ledger.items() if "qtyMinus" in path), None)
    assert minus_entry is not None, "the revealed stepper's decrement button must be inventoried"

    parsed_options = [describe_options_from_rows(*c["options"]) for c in ledger.values()]
    stepper_kinds = [p["kind"] for p in parsed_options if p]
    assert "stepper" in stepper_kinds, "the revealed stepper's own control must be recorded as a stepper"
    assert minus_entry["tag"] == "button", "must have real descriptive fields, not a ghost-node blank"

    plus_entry = next((c for path, c in ledger.items() if "qtyPlus" in path), None)
    assert plus_entry is not None


def test_static_text_content_captured_as_distinct_kind(fixture_server):
    """Phase 4: non-interactive prose gets its own TextContent record kind,
    separate from Component - and a <p> nested inside a button is excluded
    (it's that button's own accessible label, already captured there)."""
    store, sink, (mech, results) = _crawl_with_graph_store(f"{fixture_server}/index.html", max_pages=15)
    page_key = next(r.url for r in results if r.url.endswith("index.html"))
    text_ledger = store.get_text_content_ledger().get(page_key, [])
    texts = {e["text"] for e in text_ledger}

    assert "Index" in texts
    assert "A paragraph of real page text, not an interactive component." in texts
    assert "First list item text" in texts
    assert "Label wrapped in a paragraph" not in texts, (
        "a <p> nested inside a button is that button's own label, not a separate text leaf"
    )

    heading = next(e for e in text_ledger if e["text"] == "Index")
    assert heading["tag"] == "h1"


def test_reveal_chain_gets_fully_drained_in_one_continuous_session(fixture_server):
    """Regression test for the exhaustive-coverage bug (2026-08-08), still
    relevant now that there's no per-visit cap at all: a reveal chain must
    get ALL of its components interacted with, within one continuous
    session (no re-navigating between reveals, which would reset same-page
    state - see crawl_site's docstring), not stop partway through."""
    store, sink, (mech, results) = _crawl_with_graph_store(
        f"{fixture_server}/chain.html", max_pages=15
    )
    chain_results = [r for r in results if r.url.endswith("chain.html")]
    assert len(chain_results) == 1, "one continuous visit, no requeue needed to finish the chain"

    page_key = chain_results[0].url
    ledger = store.get_component_ledger()[page_key]
    all_interacted = [c for path, c in ledger.items() if path.split("#")[-1].startswith("c") and c["tag"] == "button"]
    assert all(c["interacted"] for c in all_interacted), "every chain button must eventually be interacted with"
    assert len(all_interacted) == 5, "all 5 chain buttons must have been discovered and inventoried"

    rows = {r["url"]: r for r in store.get_progress_table_rows()}
    assert rows[page_key]["status"] == "Finished", "must be marked Finished once genuinely fully drained"


# A page that generates genuinely new content on every interaction, forever
# (this project's old infinite_reveal.html fixture: every click always spawns
# exactly one more new button) has no automated regression test - there is no
# longer any cap to bound it against, so a test exercising it would hang
# rather than assert. Removed deliberately along with the fixture file. See
# docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop's
# note on this being an accepted, not a mitigated, tradeoff.
