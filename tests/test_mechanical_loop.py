"""Regression tests for MechanicalCrawler (spiders/orchestration/mechanical_loop.py),
Phase 2 of the crawl4ai migration - the mechanical, no-AI, no-per-step-decision
interaction loop that replaces SimplePRDGenerator._execute_loop.

Each test targets one of the algorithm's specific branch points named in the
plan: URL-frontier link following + dedup, same-page-reveal chaining, click-
triggered navigation being queued rather than followed inline, and the
per-page element budget cap.

Note on multi-pass pages: a page with more than one initially-visible
navigating element (a real `<a href>`, or an onclick that changes
`location`) cannot be fully interacted with in a single visit - the first
navigating click physically moves the session's page away, so the pass stops
there (see `_visit_page`'s docstring) and the page is re-queued for a
follow-up pass. Tests against such a page therefore aggregate interactions
across every `PageVisitResult` for that URL, not just the first one.
"""
import asyncio
import http.server
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.interfaces import PageState
from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.interaction_tracker import InMemoryInteractionTracker
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from database.memory_graph_store import InMemoryGraphStore
from utils.urls import route_shape

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"


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


def _crawl(start_url: str, **kwargs):
    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(**kwargs))
            results = await mech.crawl_site(start_url)
            return mech, results

    return asyncio.run(run())


def _all_interactions_for(results, suffix: str):
    """Union of interactions across every pass for the page whose URL ends
    with `suffix` - see module docstring on why a page can take >1 pass."""
    out = []
    for r in results:
        if r.url.endswith(suffix):
            out.extend(r.interactions)
    return out


def test_url_frontier_follows_links_and_dedups(fixture_server):
    """Every reachable page gets visited, including one that links back to an
    already-visited page (index.html <-> page-b.html) - the back-link must
    not cause a duplicate crawl of a page already fully drained."""
    mech, results = _crawl(f"{fixture_server}/index.html", max_pages=15)
    visited_urls = {r.url for r in results}
    assert any(u.endswith("index.html") for u in visited_urls)
    assert any(u.endswith("page-b.html") for u in visited_urls)
    assert any(u.endswith("chain.html") for u in visited_urls)
    # Once a page's pass completes without interruption, it's marked visited
    # and never queued again - confirmed by page-b.html (which links back to
    # index.html) not causing unbounded re-visits.
    assert len(results) < 15


def test_same_page_reveal_chain_gets_interacted_within_available_passes(fixture_server):
    """A click that reveals a new same-URL element must get that new element
    interacted with too, not just the first-discovered layer - even if it
    takes more than one visit-pass to reach, once earlier navigating
    elements on the same page have been drained out of the way."""
    mech, results = _crawl(f"{fixture_server}/index.html", max_pages=15)
    interactions = _all_interactions_for(results, "index.html")
    clicked_paths = {i.path for i in interactions if i.action == "click" and not i.error}
    assert any("reveal1" in p for p in clicked_paths)
    assert any("reveal2" in p for p in clicked_paths), "same-page reveal must chain"
    assert any("leafBtn" in p for p in clicked_paths), "second-level reveal must also chain"


def test_click_triggered_navigation_is_queued_not_followed_inline(fixture_server):
    """A click that navigates to a different URL (the JS-nav button) must be
    recorded with the correct resulting_url, and must stop that pass rather
    than being followed inline - and the destination page must appear as its
    own, separately-visited page result."""
    mech, results = _crawl(f"{fixture_server}/index.html", max_pages=15)
    interactions = _all_interactions_for(results, "index.html")
    js_nav = next(i for i in interactions if "jsNav" in i.path)
    assert js_nav.action == "click"
    assert not js_nav.error
    assert js_nav.resulting_url.endswith("page-b.html")
    assert any(r.url.endswith("page-b.html") for r in results)
    # The pass containing the jsNav click must have stopped there, not kept
    # going against a page that had already navigated away.
    interrupted_passes = [r for r in results if r.url.endswith("index.html") and r.interrupted_by_navigation]
    assert interrupted_passes


def test_fillable_field_gets_placeholder_value_and_is_recorded_as_fill(fixture_server):
    mech, results = _crawl(f"{fixture_server}/index.html", max_pages=15)
    interactions = _all_interactions_for(results, "index.html")
    fill = next(i for i in interactions if i.action == "fill")
    assert fill.value  # never empty - see default_placeholder_fill_value's docstring
    assert not fill.error


def test_already_interacted_components_are_skipped_on_full_revisit(fixture_server):
    """Consult-before-act: re-crawling from scratch with a tracker that
    already has every component of a page marked interacted must produce
    zero new interactions on that page, and the page completes in a single,
    non-interrupted pass (nothing left to trigger a navigating click)."""
    tracker = InMemoryInteractionTracker()

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, tracker=tracker, config=MechanicalCrawlerConfig(max_pages=15))
            await mech.crawl_site(f"{fixture_server}/index.html")
            mech2 = MechanicalCrawler(crawler, tracker=tracker, config=MechanicalCrawlerConfig(max_pages=15))
            return await mech2.crawl_site(f"{fixture_server}/index.html")

    results = asyncio.run(run())
    interactions = _all_interactions_for(results, "index.html")
    assert interactions == []


# --- Scripted-fake crawler doubles -----------------------------------------
# Per wiki/debugging-agent-systems.md's "reproduce with a deterministic,
# scripted fake" discipline: the two failure modes below (a DOM remount
# invalidating already-queued selectors; a site minting a fresh per-visit
# session-token URL forever) were both confirmed live against empanad.app but
# depend on real-site specifics (Radix UI id churn, a live redirect) that a
# real-browser fixture can't reproduce deterministically/quickly. A duck-typed
# double implementing Crawl4AICrawler's four async methods
# (discover_page/click/fill/resync) drives MechanicalCrawler exactly the same
# way the real crawler does, with the failure scripted instead of incidental.

def _component(path: str, text: str, tag: str = "button") -> Dict[str, Any]:
    return {
        "tag": tag, "text": text, "path": path, "role": "", "form": "",
        "name": "", "input_type": "", "visible": True,
    }


class _FakeStaleSelectorCrawler:
    """Reproduces the empanad.app "stale-selector cascade" symptom: clicking
    `trigger_path` succeeds and reveals nothing new (isolating this fixture
    from the pre-existing, unrelated same-page-reveal mechanism), but two
    other already-queued components have gone stale as an unrelated side
    effect (a DOM remount) - `c_old_path` is gone for good, `b_old_path`'s
    element still exists under a new id (`b_new_path`, same tag/role/text) -
    `resync()` is what `_visit_page` calls to discover that.
    """

    def __init__(self) -> None:
        self.url = "http://fixture/page"
        self.trigger_path = "body > button#trigger"
        self.c_old_path = "body > button#c_old"  # genuinely gone after remount
        self.b_old_path = "body > button#b_old"  # remounted under a new id
        self.b_new_path = "body > button#b_new"
        self.resync_calls = 0
        self.clicked: List[str] = []

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(
            url=self.url,
            components=[
                _component(self.trigger_path, "Trigger"),
                _component(self.c_old_path, "Item C"),
                _component(self.b_old_path, "Item B"),
            ],
        )

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.clicked.append(selector)
        if selector not in (self.trigger_path, self.b_new_path):
            raise RuntimeError(f"element not found: {selector}")
        # Steady-state response for a successful click - same components as
        # discovery, nothing new revealed (see class docstring).
        return PageState(
            url=self.url,
            components=[
                _component(self.trigger_path, "Trigger"),
                _component(self.b_new_path, "Item B"),
            ],
        )

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        self.resync_calls += 1
        # Ground truth after the remount: c is gone entirely, b survives
        # under a new id with the same content identity.
        return PageState(
            url=self.url,
            components=[
                _component(self.trigger_path, "Trigger"),
                _component(self.b_new_path, "Item B"),
            ],
        )


def test_stale_selector_after_remount_is_resynced_and_remapped():
    """The literal bug confirmed live on empanad.app: an "element not found"
    failure on one component (c_old) must trigger a resync that rescues a
    *later* frontier item (b_old) whose selector went stale for the same
    underlying reason, remapping it to its post-remount identity-equivalent
    path (b_new) instead of leaving it to fail identically. A third item
    (d, added below) that has no identity match in the fresh snapshot must be
    dropped distinctly (`stale=True`), not silently lost and not recorded as
    a generic error."""
    fake = _FakeStaleSelectorCrawler()
    d_old_path = "body > button#d_old"

    real_discover = fake.discover_page

    async def discover_with_d(url, session_id=None):
        state = await real_discover(url, session_id)
        state.components.append(_component(d_old_path, "Item D"))
        return state

    fake.discover_page = discover_with_d

    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=1))
    results = asyncio.run(mech.crawl_site(fake.url))
    interactions = results[0].interactions

    c_failure = next(i for i in interactions if i.path == fake.c_old_path)
    assert c_failure.error and not c_failure.stale

    d_failure = next(i for i in interactions if i.path == d_old_path)
    assert d_failure.stale and not d_failure.error

    b_success = next(i for i in interactions if i.path == fake.b_new_path)
    assert not b_success.error and not b_success.stale

    # The stale old path was never itself attempted - only its remapped
    # replacement was - and only one resync ran for the whole streak of
    # consecutive failures (c failing, then d being unresolvable), not one
    # per failure.
    assert fake.b_old_path not in fake.clicked
    assert fake.resync_calls == 1


class _FakeTokenSiteCrawler:
    """Reproduces the empanad.app "unbounded per-session-token frontier"
    symptom: every visited page links to exactly one freshly-minted token
    instance of the *same* route shape (confirmed live: 10 distinct
    `/o/<hash>` tokens across two real runs) - without route-shape bounding,
    this chain never terminates on its own."""

    def __init__(self) -> None:
        self.visit_count = 0

    async def discover_page(self, url: str, session_id=None) -> PageState:
        self.visit_count += 1
        next_token = f"session{self.visit_count}XyZ1234567890"
        next_url = f"http://fixture/o/{next_token}"
        return PageState(url=url, components=[], links=[{"href": next_url, "scheme": "http"}])

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        raise AssertionError("fixture has no components to click")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no components to fill")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


class _FakeSessionTokenPageCrawler:
    """Two literal hash-instance URLs of the *same* route shape
    (`/o/<hash1>`, `/o/<hash2>`) - reproducing the real empanad.app case
    directly: the literal URL differs every visit, but it's the same
    underlying templated screen, so both expose an identical single
    component. `url2` is only ever reached via a link discovered on `url1`'s
    page (the URL frontier), never via a same-session click - isolates this
    fixture from physical-navigation-interruption behavior (already covered
    by test_click_triggered_navigation_is_queued_not_followed_inline) and
    focuses purely on canonical storage identity across two real page visits.
    """

    def __init__(self) -> None:
        self.url1 = "http://fixture/o/aB1cD2eF3gH4iJ5kL6mN"
        self.url2 = "http://fixture/o/zY9xW8vU7tS6rQ5pO4nM"
        self.item_path = "body > button#item"

    async def discover_page(self, url: str, session_id=None) -> PageState:
        other = self.url2 if url == self.url1 else self.url1
        return PageState(
            url=url,
            components=[_component(self.item_path, "Item")],
            links=[{"href": other, "scheme": "http"}],
        )

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        return PageState(url=url, components=[_component(self.item_path, "Item")])

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_same_route_shape_pages_collapse_to_one_canonical_graph_node():
    """The actual feature request this was built for: two literal
    session-token instances of what a human recognizes as one screen must
    become ONE GraphStore node with a merged component ledger, not two
    near-duplicate ones - even though both are real, distinct page visits
    (clean_url() correctly keeps their literal identities apart; only the
    *canonical storage* key collapses, per route_shape()'s docstring)."""
    fake = _FakeSessionTokenPageCrawler()
    assert route_shape(fake.url1) == route_shape(fake.url2)  # same shape, different literal URL

    store = InMemoryGraphStore()
    store.connect()
    sink = GraphStoreSink(store, "fixture")
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(sink=sink, max_pages=5, max_visits_per_route_shape=2))
    results = asyncio.run(mech.crawl_site(fake.url1))

    # Both literal pages really were visited...
    assert len(results) == 2
    assert {r.url for r in results} == {route_shape(fake.url1)}

    # ...but GraphStore only ever recorded one canonical node for them.
    rows = store.get_progress_table_rows("fixture")
    assert len(rows) == 1
    assert rows[0]["url"] == route_shape(fake.url1)

    # The second visit's identical component was already covered by the
    # first (consult-before-act against the shared canonical page_key) - so
    # only one real click ever happened across both visits combined.
    all_interactions = [i for r in results for i in r.interactions]
    successful_clicks = [i for i in all_interactions if i.action == "click" and not i.error and not i.stale]
    assert len(successful_clicks) == 1


def test_route_shape_bounding_stops_unbounded_session_token_growth():
    """A site whose every page links to a freshly-minted token instance of
    the same route shape must not grow the URL frontier forever -
    max_visits_per_route_shape bounds it independent of max_pages (which has
    to stay generous/unset for this kind of site, per pragma.example.yaml)."""
    start_url = "http://fixture/o/" + "A" * 20

    fake_default = _FakeTokenSiteCrawler()
    mech_default = MechanicalCrawler(fake_default, config=MechanicalCrawlerConfig(max_pages=1000, max_visits_per_route_shape=1))
    results_default = asyncio.run(mech_default.crawl_site(start_url))
    assert len(results_default) <= 3  # bounded - would run to max_pages (1000) if unbounded

    fake_raised = _FakeTokenSiteCrawler()
    mech_raised = MechanicalCrawler(fake_raised, config=MechanicalCrawlerConfig(max_pages=1000, max_visits_per_route_shape=4))
    results_raised = asyncio.run(mech_raised.crawl_site(start_url))
    assert len(results_raised) > len(results_default)  # raising the knob samples more instances
    assert len(results_raised) <= 6


class _FakeFanOutCrawler:
    """A "hub" page linking to `num_leaves` independent leaf pages, each
    taking a fixed, simulated amount of work (`asyncio.sleep`) to visit -
    real per-interaction work in a live crawl is dominated by fixed
    `wait_seconds`/`interaction_wait_seconds` sleeps (confirmed via a real
    run's own debug log, see MechanicalCrawler's class docstring), so a
    simulated sleep is a faithful, deterministic stand-in without needing a
    real browser. Tracks how many `discover_page` calls were ever
    simultaneously in flight, to prove page_concurrency actually overlaps
    work rather than just accepting the parameter.
    """

    def __init__(self, num_leaves: int = 5, work_seconds: float = 0.05) -> None:
        self.start_url = "http://fixture/hub"
        self.leaf_urls = [f"http://fixture/leaf{i}" for i in range(num_leaves)]
        self.work_seconds = work_seconds
        self.in_flight = 0
        self.max_in_flight = 0

    async def discover_page(self, url: str, session_id=None) -> PageState:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.work_seconds)
        finally:
            self.in_flight -= 1
        if url == self.start_url:
            links = [{"href": u, "scheme": "http"} for u in self.leaf_urls]
            return PageState(url=url, components=[], links=links)
        return PageState(url=url, components=[])

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        raise AssertionError("fixture has no components to click")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no components to fill")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_page_concurrency_set_to_one_is_fully_sequential():
    """page_concurrency=1 must still reproduce the original single-worker
    behavior exactly - every page still visited, but never more than one
    `discover_page` in flight at once. (The default is no longer 1 - see
    PragmaConfig.page_concurrency for why - so this pins the explicit-1 case.)"""
    fake = _FakeFanOutCrawler(num_leaves=5, work_seconds=0.05)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10, page_concurrency=1))
    results = asyncio.run(mech.crawl_site(fake.start_url))
    assert len(results) == 6  # hub + 5 leaves
    assert fake.max_in_flight == 1


def test_page_concurrency_raised_visits_pages_in_parallel():
    """The actual feature this was built for: raising page_concurrency must
    cause real overlap between page visits, not just accept the parameter -
    this is the only lever that gets a large crawl's wall-clock time down
    (see MechanicalCrawler's class docstring)."""
    fake = _FakeFanOutCrawler(num_leaves=5, work_seconds=0.05)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10, page_concurrency=4))
    results = asyncio.run(mech.crawl_site(fake.start_url))
    assert len(results) == 6  # every page still visited, same as sequential
    assert {r.url for r in results} == {"fixture/hub"} | {f"fixture/leaf{i}" for i in range(5)}
    assert fake.max_in_flight > 1  # real concurrent overlap happened


def test_effective_concurrency_is_full_below_the_taper_start_ratio():
    """A healthy target (target_slowdown_ratio at or under the taper start)
    must not reduce concurrency at all - only real degradation should."""
    fake = _FakeFanOutCrawler()
    fake.target_slowdown_ratio = 1.3
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(page_concurrency=4))

    assert mech._pacing.effective_concurrency() == 4


def test_effective_concurrency_tapers_linearly_between_start_and_end_ratio():
    """Partway through the taper range, effective concurrency must sit
    partway between page_concurrency and min_page_concurrency, not jump
    straight to the floor - a gradual response to gradually worsening
    conditions."""
    fake = _FakeFanOutCrawler()
    fake.target_slowdown_ratio = 3.0  # midpoint of the default 2.0-4.0 taper range
    mech = MechanicalCrawler(
        fake, config=MechanicalCrawlerConfig(page_concurrency=5, min_page_concurrency=1)
    )

    assert mech._pacing.effective_concurrency() == 3  # halfway between 5 and 1


def test_effective_concurrency_floors_at_min_page_concurrency_when_severely_degraded():
    """At or beyond the taper end ratio, effective concurrency must not drop
    below min_page_concurrency - some progress must always be possible."""
    fake = _FakeFanOutCrawler()
    fake.target_slowdown_ratio = 10.0  # far past the default 4.0 taper end
    mech = MechanicalCrawler(
        fake, config=MechanicalCrawlerConfig(page_concurrency=4, min_page_concurrency=1)
    )

    assert mech._pacing.effective_concurrency() == 1


def test_effective_concurrency_reads_as_healthy_when_crawler_has_no_slowdown_signal():
    """A fake/test crawler with no target_slowdown_ratio attribute at all
    must read as healthy (full concurrency), not as degraded."""
    fake = _FakeFanOutCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(page_concurrency=4))

    assert mech._pacing.effective_concurrency() == 4


def test_target_degradation_caps_real_concurrent_overlap_below_page_concurrency():
    """The actual end-to-end behavior: a target already reporting severe
    degradation before the crawl starts must keep max_in_flight at
    min_page_concurrency, even though page_concurrency itself is much
    higher - concurrency must genuinely shrink, not just get slower per
    request (that's Crawl4AICrawler's own backoff, a separate mechanism)."""
    fake = _FakeFanOutCrawler(num_leaves=5, work_seconds=0.05)
    fake.target_slowdown_ratio = 10.0  # severely degraded from the very first check
    mech = MechanicalCrawler(
        fake,
        config=MechanicalCrawlerConfig(max_pages=10, page_concurrency=4, min_page_concurrency=1),
    )
    results = asyncio.run(mech.crawl_site(fake.start_url))

    assert len(results) == 6  # every page still visited - just not concurrently
    assert fake.max_in_flight == 1


class _FakeRedirectingEntryCrawler:
    """Reproduces the empanad.app entry-redirect bug directly: the *bare*
    entry URL mints a brand-new session/hash on every single request -
    discover_page(bare_url) never lands on the same destination twice. A
    click on the resolved page navigates elsewhere (triggering
    interrupted_by_navigation), forcing a follow-up-pass requeue - the
    literal case the bug was found in. Any *other* literal URL (a resolved
    hash, or the navigation target) is directly addressable and returns
    itself unchanged, exactly like a real order-confirmation URL being
    revisitable on its own once already minted.
    """

    def __init__(self) -> None:
        self.bare_url = "http://fixture/"
        self.hash_counter = 0
        self.requested_urls: List[str] = []
        self.item_path = "body > button#item"
        self.nav_path = "body > a#navlink"
        self._current_page_by_session: Dict[str, str] = {}

    def _new_hash_url(self) -> str:
        self.hash_counter += 1
        return f"http://fixture/o/hash{self.hash_counter}"

    def _components(self) -> List[Dict[str, Any]]:
        return [_component(self.item_path, "Item"), _component(self.nav_path, "Nav", tag="a")]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        self.requested_urls.append(url)
        dest = self._new_hash_url() if url == self.bare_url else url
        self._current_page_by_session[session_id] = dest
        return PageState(url=dest, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        if selector == self.nav_path:
            dest = "http://fixture/elsewhere"
            self._current_page_by_session[session_id] = dest
            return PageState(url=dest, components=[])
        # Item click: no navigation - stays on this session's current
        # resolved page, exactly like a real js_only interaction does
        # (crawl4ai's own click() never re-navigates - see
        # crawl4ai_crawler.py's click() docstring).
        current = self._current_page_by_session[session_id]
        return PageState(url=current, components=self._components())

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


class _FakeSpaStateTransitionCrawler:
    """Reproduces the empanad.app "start order" symptom directly: a click
    never navigates (browser URL identical before/after - `navigated: False`
    throughout in the real debug log) but almost the entire DOM is replaced
    (the landing screen's own button is gone; an unrelated order-flow screen
    appears in its place). The mechanical loop must recognize this as an
    in-page *state transition* (a new graph node), not merge it into the
    landing screen's own component ledger the way an ordinary reveal (most
    of the page survives, plus a few new items - e.g. a dropdown opening) is
    merged.
    """

    def __init__(self) -> None:
        self.url = "http://fixture/spa"
        self.start_path = "body > button#start_order"
        self.confirm_path = "body > button#confirm_order"
        self.other_path = "body > button#other_action"

    def _order_screen_components(self) -> List[Dict[str, Any]]:
        return [
            _component(self.confirm_path, "Confirm Order"),
            _component(self.other_path, "Something Else"),
        ]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(url=self.url, title="EmpanadApp", components=[_component(self.start_path, "Start Order")])

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        if selector == self.start_path:
            return PageState(url=self.url, title="EmpanadApp", components=self._order_screen_components())
        if selector in (self.confirm_path, self.other_path):
            return PageState(url=self.url, title="EmpanadApp", components=self._order_screen_components())
        raise AssertionError(f"unexpected click {selector!r}")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_full_screen_replace_becomes_a_new_state_node_not_a_merged_reveal():
    fake = _FakeSpaStateTransitionCrawler()
    store = InMemoryGraphStore()
    store.connect()
    sink = GraphStoreSink(store, "fixture")
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(sink=sink, max_pages=1))
    results = asyncio.run(mech.crawl_site(fake.url))

    result = results[0]
    start_interaction = next(i for i in result.interactions if i.path == fake.start_path)
    assert not start_interaction.error
    # Physically never navigated - same literal URL before and after.
    assert start_interaction.resulting_url == route_shape(fake.url)

    assert result.state_transitions, "the full-screen replace must be recorded as a state transition"
    new_key = result.state_transitions[0]
    assert new_key != route_shape(fake.url)

    # GraphStore ends up with TWO page nodes, not one blob - the landing
    # screen and the order-flow screen it transitioned into.
    keys = {row["url"] for row in store.get_progress_table_rows("fixture")}
    assert route_shape(fake.url) in keys
    assert new_key in keys

    # The new node's components carry real descriptive facts (not the
    # blank-field ghost-node shape graph-based-crawl-tracking.md's fix
    # guards against elsewhere).
    new_components = store.get_component_states("fixture", new_key)
    assert new_components[fake.confirm_path]["text"] == "Confirm Order"

    # An edge connects the two nodes, attributed to the trigger.
    loop_signals = store.get_loop_signals("fixture", new_key)
    assert any(s["component"] == fake.start_path for s in loop_signals)

    # The new screen's own components get interacted with too, under the
    # new node's namespace - the pass didn't just detect the transition and
    # stop, it kept exploring.
    successful_paths = {i.path for i in result.interactions if not i.error}
    assert fake.confirm_path in successful_paths
    assert fake.other_path in successful_paths


def test_ordinary_same_page_reveal_is_not_misclassified_as_a_state_transition(fixture_server):
    """A dropdown-style reveal (index.html's reveal1/reveal2/leafBtn chain -
    everything already on the page survives, only new items get added) must
    still take the pre-existing merge-into-same-node path, not the new
    state-transition one - the overlap heuristic must not fire on the common
    case it has to coexist with."""
    _, results = _crawl(f"{fixture_server}/index.html", max_pages=15)
    index_results = [r for r in results if r.url.endswith("index.html")]
    assert index_results
    assert all(not r.state_transitions for r in index_results)


def test_interrupted_navigation_requeues_resolved_url_not_original_request():
    """The real bug found live on empanad.app: a follow-up pass after
    interrupted_by_navigation must re-request the already-*resolved*
    destination, not the originally-requested literal URL - re-requesting a
    redirecting entry point a second time mints an entirely new session
    instead of resuming the one this pass was still working on, silently
    abandoning its undrained frontier and burning a real, unnecessary extra
    fetch in the process."""
    fake = _FakeRedirectingEntryCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10))
    asyncio.run(mech.crawl_site(fake.bare_url))

    # The bare, redirecting entry point was only ever requested once - the
    # follow-up pass did NOT re-request it (which would have minted a second,
    # unrelated session and abandoned the first one's frontier).
    assert fake.requested_urls.count(fake.bare_url) == 1
    assert fake.hash_counter == 1

    # The follow-up pass instead re-requested the already-resolved
    # destination directly.
    assert "http://fixture/o/hash1" in fake.requested_urls


class _FakeExternalLinkCrawler:
    """A page linking to both an in-scope page (same host) and an
    out-of-scope one (a different host entirely) - the ordinary "discovered
    link" path `is_in_scope()`/`_enqueue` must gate."""

    def __init__(self) -> None:
        self.start_url = "http://fixture.example/index"
        self.internal_url = "http://fixture.example/other"
        self.external_url = "http://evil.example/page"

    async def discover_page(self, url: str, session_id=None) -> PageState:
        if url == self.start_url:
            return PageState(
                url=url,
                components=[],
                links=[
                    {"href": self.internal_url, "scheme": "http"},
                    {"href": self.external_url, "scheme": "http"},
                ],
            )
        return PageState(url=url, components=[])

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        raise AssertionError("fixture has no components to click")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_external_domain_link_is_never_visited():
    """The actual feature this was built for: a link to a different site
    entirely must never get crawled, even though it's a completely ordinary,
    successfully-discovered link - only the same-host page gets visited."""
    fake = _FakeExternalLinkCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10))
    results = asyncio.run(mech.crawl_site(fake.start_url))

    visited_urls = {r.url for r in results}
    assert "fixture.example/other" in visited_urls
    assert not any("evil.example" in u for u in visited_urls)
    assert len(results) == 2  # start page + the one in-scope link, nothing external


class _FakeExternalRedirectCrawler:
    """Reproduces "the scraper gets out of the base URL due to a redirect":
    a click on an otherwise ordinary component navigates the live session to
    a completely different host - out of scope, and must never itself be
    visited, even though the click that led there is a real, successfully-
    completed interaction."""

    def __init__(self) -> None:
        self.start_url = "http://fixture.example/index"
        self.away_path = "body > a#away"
        self.other_path = "body > button#other"

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(
            url=self.start_url,
            components=[
                _component(self.away_path, "Away", tag="a"),
                _component(self.other_path, "Other"),
            ],
        )

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        if selector == self.away_path:
            return PageState(url="http://evil.example/landed", components=[])
        return PageState(
            url=self.start_url,
            components=[
                _component(self.away_path, "Away", tag="a"),
                _component(self.other_path, "Other"),
            ],
        )

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_redirect_to_external_domain_stops_the_pass_but_never_gets_crawled():
    """A click-triggered redirect that lands outside the crawl's own site
    must still stop the interrupted pass (it's a real navigation - the live
    session did leave the page, per crawl4ai-integration-pitfalls.md's
    "must stop that page's work immediately" entry) and requeue the
    *originating* page to finish its own frontier, exactly like an ordinary
    same-site navigation interruption - but the external destination itself
    must never be enqueued/visited."""
    fake = _FakeExternalRedirectCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10))
    results = asyncio.run(mech.crawl_site(fake.start_url))

    assert not any("evil.example" in r.url for r in results)
    assert any(r.interrupted_by_navigation for r in results)

    # The originating page's frontier still gets fully drained across its
    # (same-host) follow-up passes - the "away" link that caused the
    # redirect, and the other, unrelated component.
    all_paths = {i.path for r in results for i in r.interactions if not i.error}
    assert fake.away_path in all_paths
    assert fake.other_path in all_paths


def test_allow_subdomains_wiring_through_mechanical_crawler():
    """allow_subdomains, threaded through from the constructor, must
    actually change is_in_scope's outcome for a discovered subdomain link -
    not just work in isolation (already covered in tests/test_urls.py)."""

    class _FakeSubdomainCrawler:
        def __init__(self) -> None:
            self.start_url = "http://example.fixture/index"
            self.sub_url = "http://blog.example.fixture/post"

        async def discover_page(self, url: str, session_id=None) -> PageState:
            if url == self.start_url:
                return PageState(url=url, components=[], links=[{"href": self.sub_url, "scheme": "http"}])
            return PageState(url=url, components=[])

        async def click(self, url, session_id, selector):
            raise AssertionError("no components")

        async def fill(self, url, session_id, selector, value):
            raise AssertionError("no components")

        async def resync(self, url, session_id):
            raise AssertionError("not exercised")

    fake_default = _FakeSubdomainCrawler()
    mech_default = MechanicalCrawler(fake_default, config=MechanicalCrawlerConfig(max_pages=10))
    results_default = asyncio.run(mech_default.crawl_site(fake_default.start_url))
    assert not any("blog.example.fixture" in r.url for r in results_default)

    fake_allowed = _FakeSubdomainCrawler()
    mech_allowed = MechanicalCrawler(fake_allowed, config=MechanicalCrawlerConfig(max_pages=10, allow_subdomains=True))
    results_allowed = asyncio.run(mech_allowed.crawl_site(fake_allowed.start_url))
    assert any("blog.example.fixture" in r.url for r in results_allowed)


class _FakeConvergingEntryRedirectsCrawler:
    """Reproduces the real bug found live on mapadeprofesionales.com
    (`page_concurrency=10`): two *different* pages (`entry_a`/`entry_b`,
    both reached from `hub`) each independently redirect, at the navigation
    level, to the identical shared destination - mirrors the site's own
    bare-domain-redirects-on-every-request pattern (already documented for
    empanad.app), just triggered from two different sources instead of one.
    Each entry point's own interaction then navigates elsewhere too, forcing
    `interrupted_by_navigation` - which is what makes the follow-up-pass
    requeue (the one path that bypasses `_enqueue`'s dedup, see
    `MechanicalCrawler._in_flight`) push the *shared* destination onto the
    frontier twice, from two unrelated call sites that have no way to know
    about each other.

    `shared`'s own `discover_page()` is instrumented (`asyncio.sleep`, same
    concurrency-proving technique as `_FakeFanOutCrawler` above) to record
    `max_in_flight_shared` - the fact this test actually exists to check.
    """

    def __init__(self, work_seconds: float = 0.05) -> None:
        self.hub = "http://fixture/hub"
        self.entry_a = "http://fixture/a"
        self.entry_b = "http://fixture/b"
        self.shared = "http://fixture/shared"
        self.nav_path = "body > a#nav"
        self.work_seconds = work_seconds
        self.in_flight_shared = 0
        self.max_in_flight_shared = 0
        self.shared_discover_calls = 0
        self.entry_clicks = 0

    async def discover_page(self, url: str, session_id=None) -> PageState:
        if url == self.hub:
            links = [{"href": self.entry_a, "scheme": "http"}, {"href": self.entry_b, "scheme": "http"}]
            return PageState(url=url, components=[], links=links)
        if url in (self.entry_a, self.entry_b):
            # Redirected, at the *navigation* level (no click involved yet),
            # to the shared destination - state.url differs from what was
            # requested right from this very first discover_page() call.
            return PageState(url=self.shared, components=[_component(self.nav_path, "Nav", tag="a")])
        if url == self.shared:
            self.shared_discover_calls += 1
            self.in_flight_shared += 1
            self.max_in_flight_shared = max(self.max_in_flight_shared, self.in_flight_shared)
            try:
                await asyncio.sleep(self.work_seconds)
            finally:
                self.in_flight_shared -= 1
            return PageState(url=self.shared, components=[_component(self.nav_path, "Nav", tag="a")])
        raise AssertionError(f"unexpected discover_page {url!r}")

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        # Navigates away regardless of which session issued it - forces
        # interrupted_by_navigation, so the follow-up requeue fires with
        # resolved_url = whatever this session's discover_page() already
        # resolved to (the shared destination, for both entry_a and entry_b).
        self.entry_clicks += 1
        await asyncio.sleep(self.work_seconds)
        return PageState(url="http://fixture/elsewhere", components=[])

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_two_pages_redirecting_to_the_same_destination_never_visit_it_concurrently():
    """The actual bug: two unrelated pages both redirecting to one shared
    destination must never result in two concurrent `_visit_page()` calls
    for that destination, even though both independently requeue it via the
    bypass-dedup follow-up-pass path - `_in_flight` must catch what
    `_enqueue`'s own `_queued` guard structurally cannot (it's never
    consulted on that path)."""
    fake = _FakeConvergingEntryRedirectsCrawler(work_seconds=0.05)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=20, page_concurrency=4))
    asyncio.run(mech.crawl_site(fake.hub))

    # Both entry points genuinely, independently triggered the vulnerable
    # code path (their own interrupted-navigation pass, each resolving to
    # and bypass-requeuing the shared destination) - otherwise "never
    # concurrent" below would be true trivially, proving nothing.
    assert fake.entry_clicks == 2

    # The actual fix: even though the shared destination was pushed onto the
    # frontier twice (once per entry point), `_in_flight` collapsed the
    # second, redundant dequeue into a no-op rather than letting two workers
    # run `_visit_page()` for it at once - proven two ways: it was only
    # really visited once, and its own discover_page() never saw >1 caller
    # inside it at the same time.
    assert fake.shared_discover_calls == 1
    assert fake.max_in_flight_shared == 1


class _FakeChurningNavLinkCrawler:
    """Reproduces the real austral.edu.ar bug directly (confirmed live via
    debug_logs/austral.edu.ar_20260808T224204Z/debug.md - a single
    `_visit_page()` call never returned across 90+ minutes and 70+ attempts):
    a persistent, site-wide nav link's `click()` call fails outright (its
    resulting-URL never gets reported cleanly - the shape a timed-out
    marker read-back on a slow destination page produces) even though the
    live browser genuinely navigated, confirmed here by `resync()` reporting
    a different URL. The SAME logical link also gets a *different* selector
    path on every fresh `discover_page()` call (framework-assigned id churn)
    - so pure path-based dedup can never recognize it as already-tried on a
    later resume.
    """

    def __init__(self) -> None:
        self.page_url = "http://fixture/page"
        self.other_url = "http://fixture/other"
        self.discover_calls = 0
        self.nav_click_attempts = 0
        self.other_component_clicked = False

    def _nav_path(self) -> str:
        return f"body > a#nav-{self.discover_calls}"  # a fresh id every reload

    def _components(self) -> List[Dict[str, Any]]:
        return [
            _component(self._nav_path(), "Encontra tu programa", tag="a"),
            _component("body > button#other", "Other"),
        ]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        if url != self.page_url:
            return PageState(url=url, components=[])
        self.discover_calls += 1
        return PageState(url=self.page_url, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        if selector.startswith("body > a#nav-"):
            self.nav_click_attempts += 1
            # The real symptom: a plain failure, no resulting_url at all -
            # even though (per resync() below) the browser really did move.
            raise RuntimeError("interaction failed: could not read back action result")
        if selector == "body > button#other":
            self.other_component_clicked = True
            return PageState(url=self.page_url, components=self._components())
        raise AssertionError(f"unexpected selector {selector!r}")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        # Ground truth: the live session really did navigate away, even
        # though click() above never got to report it.
        return PageState(url=self.other_url, components=[])


def test_failed_click_that_silently_navigated_is_detected_and_not_retried_after_resume():
    """The actual fix: a click failure that turns out to be a silently-missed
    navigation must (1) stop the pass immediately - not grind through the
    rest of a large frontier against a page the session already left - and
    (2) never be re-attempted on a later resume, even though the same
    logical component gets a brand-new selector path on every fresh
    discover_page() call. Not a retry-count cap - the crawl must converge
    because the component's *content* identity, not its path, is what's
    remembered."""
    fake = _FakeChurningNavLinkCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10))
    results = asyncio.run(mech.crawl_site(fake.page_url))

    # The nav link's failure was only ever attempted ONCE across the whole
    # crawl - not once per resume (which, before the fix, would grow
    # without bound as long as its selector kept churning).
    assert fake.nav_click_attempts == 1

    # The pass that hit the silent navigation stopped immediately - it did
    # not also try the (still-there) "other" component in that same doomed
    # attempt against the wrong live page.
    page_results = [r for r in results if r.url.endswith("fixture/page")]
    assert any(r.interrupted_by_navigation for r in page_results)

    # The resumed pass, on its fresh discover_page() (a new nav-N path),
    # correctly skipped the known-navigating link and reached the other,
    # harmless component instead - the crawl actually converges.
    assert fake.other_component_clicked is True
    assert fake.discover_calls == 2  # initial visit + exactly one resume, not dozens


class _FakeMixedFailureCrawler:
    """Reproduces the second-order bug found live on austral.edu.ar
    (debug_logs/austral.edu.ar_20260809T011221Z/debug.md): a pass with an
    EARLIER "element not found" failure (which consumes the stale-selector
    resync's own guard) must not starve a LATER, unrelated silent-navigation
    check for a *different* failing component in the same pass - stale-
    selector recovery and silent-navigation detection are two different
    recoveries and need two independent "once per streak" guards, not one
    shared one.
    """

    def __init__(self) -> None:
        self.page_url = "http://fixture/page"
        self.other_url = "http://fixture/other"
        self.discover_calls = 0
        self.resync_calls = 0
        self.nav_click_attempts = 0
        self.stale_path = "body > button#stale"

    def _nav_path(self) -> str:
        return f"body > a#nav-{self.discover_calls}"  # churns every reload

    def _components(self) -> List[Dict[str, Any]]:
        return [
            _component(self.stale_path, "Stale"),
            _component(self._nav_path(), "Encontra tu programa", tag="a"),
        ]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        if url != self.page_url:
            return PageState(url=url, components=[])
        self.discover_calls += 1
        return PageState(url=self.page_url, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        if selector == self.stale_path:
            raise RuntimeError(f"element not found: {selector}")
        if selector.startswith("body > a#nav-"):
            self.nav_click_attempts += 1
            raise RuntimeError("interaction failed: could not read back action result")
        raise AssertionError(f"unexpected selector {selector!r}")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        self.resync_calls += 1
        if self.resync_calls == 1:
            # The stale-selector recovery's own resync, called right after
            # the "element not found" failure above - the browser hasn't
            # moved yet at this point, still on page_url.
            return PageState(url=self.page_url, components=self._components())
        # A later resync (from the silent-navigation check, after the nav
        # link's own failure) - the browser has genuinely moved by now.
        return PageState(url=self.other_url, components=[])


def test_stale_selector_recovery_does_not_starve_a_later_silent_navigation_check():
    """The actual second-order fix: an "element not found" failure earlier
    in a pass must not consume the *same* guard a later, unrelated
    silent-navigation check needs - each failure kind gets its own
    independent one-per-streak allowance."""
    fake = _FakeMixedFailureCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=10))
    asyncio.run(mech.crawl_site(fake.page_url))

    # The nav link was attempted, and its content identity was learned from
    # that single attempt - not re-attempted on the resumed pass, even
    # though an unrelated stale-selector failure happened earlier in the
    # very same pass.
    assert fake.nav_click_attempts == 1
    assert fake.discover_calls == 2  # initial visit + exactly one resume


class _FakeChurningWidgetCrawler:
    """Reproduces the real austral.edu.ar bug directly (the libro_UA30 book
    viewer, confirmed via
    debug_logs/austral.edu.ar_20260809T144836Z/debug.md - 155+ same-page
    interactions in a row, `navigated: False`, `success: True` every single
    time): a same-page widget (e.g. a page-turn/thumbnail-strip control)
    re-renders under a *fresh* path on every interaction, but with the
    identical content identity - so the ordinary same-page-reveal frontier,
    which only tracks *paths*, keeps treating every fresh render as
    genuinely new, never-before-seen work, forever.
    """

    def __init__(self) -> None:
        self.page_url = "http://fixture/page"
        self.click_count = 0

    def _widget_path(self) -> str:
        return f"body > button#widget-{self.click_count}"

    def _components(self) -> List[Dict[str, Any]]:
        return [_component(self._widget_path(), "Next", tag="button")]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(url=self.page_url, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.click_count += 1
        # Same page, same URL - but a "new" (freshly-pathed) instance of the
        # identical widget reappears every time, exactly like a re-rendered
        # thumbnail-strip control.
        return PageState(url=self.page_url, components=self._components())

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_churning_same_page_widget_converges_instead_of_looping_forever():
    """The actual fix: a same-page widget that re-renders under a fresh path
    on every interaction must be recognized, by content identity, as already
    handled - not re-offered as "new" work on every single reveal, which
    would otherwise never converge. There is no numeric interaction ceiling
    to fall back on if this dedup were wrong (see
    docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop) -
    this test is the actual backstop against an infinite same-page loop."""
    fake = _FakeChurningWidgetCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=5))
    results = asyncio.run(mech.crawl_site(fake.page_url))

    # Converged after exactly one real click - the second, "freshly
    # rendered" instance was correctly recognized as the same widget by
    # content identity and never re-offered.
    assert fake.click_count == 1
    assert not any(r.interrupted_by_navigation for r in results)


class _FakeDeadSessionCrawler:
    """Reproduces the third austral.edu.ar bug found live (debug_logs/
    austral.edu.ar_20260810T152449Z/debug.md - one `_visit_page()` call still
    running after 40+ minutes and 40+ identical failures when last read): a
    click navigates the session to a page that never finishes loading (a WAF
    holding the response open as an anti-automation measure - the real
    destination was an 8653-byte, `<body>`-less shell), so EVERY subsequent
    interaction against that session - including `resync()`'s own attempt to
    confirm the navigation - fails the exact same, unexplained way. Unlike
    `_FakeChurningNavLinkCrawler` above (where `resync()` reliably confirms
    the navigation, letting the pass stop cleanly after one check), here
    `resync()` itself is just another doomed interaction against the same
    dead session - the one recovery built to catch this can never fire.
    """

    def __init__(self, n_remaining: int = 20) -> None:
        self.page_url = "http://fixture/page"
        self.n_remaining = n_remaining
        self.click_attempts = 0
        self.resync_attempts = 0

    def _components(self) -> List[Dict[str, Any]]:
        return [_component("body > a#nav", "Go", tag="a")] + [
            _component(f"body > button#item{i}", f"Item {i}") for i in range(self.n_remaining)
        ]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(url=self.page_url, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.click_attempts += 1
        # Every click - including whichever one actually navigated - fails
        # the same generic way a slow/dead destination's marker read-back
        # does (see Crawl4AICrawler._interact's docstring).
        raise RuntimeError("interaction failed: Timeout 30000ms exceeded")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        # The one check meant to confirm "did we silently navigate" is
        # itself just another interaction against the same dead session - it
        # fails identically, every single time, never confirming anything.
        self.resync_attempts += 1
        raise RuntimeError("interaction failed: Timeout 30000ms exceeded")


def test_consecutive_unexplained_failures_stop_the_pass_when_silent_nav_check_is_also_inconclusive():
    """The circuit-breaker fix: when the silent-navigation check itself can
    never confirm anything (because it's just another interaction against a
    session that's genuinely dead), the pass must still give up well before
    attempting every remaining frontier item one at a time - not grind
    through all of them, each burning a full interaction timeout, for
    however many components the page happens to have."""
    fake = _FakeDeadSessionCrawler(n_remaining=20)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(max_pages=1))
    results = asyncio.run(mech.crawl_site(fake.page_url))

    # Nowhere near all 21 components (1 nav link + 20 "item" buttons) were
    # attempted - the circuit breaker cut the pass short instead of grinding
    # through the whole frontier.
    assert fake.click_attempts < 10

    # The pass is honestly marked as interrupted (not silently "finished"
    # with most of the page never actually explored).
    page_results = [r for r in results if r.url.endswith("fixture/page")]
    assert any(r.interrupted_by_navigation for r in page_results)


class _FakeSessionRecordingCrawler:
    """A flat fan-out from one root: `n_pages` leaf pages, each with a
    single non-navigating "item" component. Records the `session_id` every
    `discover_page` call ran under, to prove distinct browser tabs stay
    capped at `page_concurrency` instead of growing by one per page
    (confirmed live on austral.edu.ar: crawl4ai's own [FETCH] timer climbed
    from ~1s to ~30-40s over one run as a new tab piled up per page,
    with nothing ever closing them)."""

    def __init__(self, n_pages: int) -> None:
        self.root_url = "http://fixture/root"
        self.leaf_urls = [f"http://fixture/leaf{i}" for i in range(n_pages)]
        self.session_ids_seen: List[str] = []

    async def discover_page(self, url: str, session_id=None) -> PageState:
        await asyncio.sleep(0)  # yield control - lets other workers interleave, like a real await would
        self.session_ids_seen.append(session_id)
        if url == self.root_url:
            links = [{"href": leaf, "scheme": "http"} for leaf in self.leaf_urls]
            return PageState(url=self.root_url, links=links)
        return PageState(url=url, components=[_component("body > button#item", "Item")])

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        # No-op click: page settles with the same single item, nothing new revealed.
        return PageState(url=url, components=[_component("body > button#item", "Item")])

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_session_count_stays_capped_at_page_concurrency_not_one_per_page():
    """Visiting many pages sequentially (page_concurrency=1) must reuse one
    browser tab throughout, not open a fresh one per page."""
    fake = _FakeSessionRecordingCrawler(n_pages=5)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(page_concurrency=1))
    asyncio.run(mech.crawl_site(fake.root_url))

    assert len(set(fake.session_ids_seen)) == 1


def test_session_count_scales_with_concurrency_not_page_count():
    """Two concurrent workers visiting many pages must still only ever use
    two distinct browser tabs between them, one per worker."""
    fake = _FakeSessionRecordingCrawler(n_pages=8)
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig(page_concurrency=2))
    asyncio.run(mech.crawl_site(fake.root_url))

    assert len(set(fake.session_ids_seen)) == 2


class _FakeSessionRecyclingCrawler(_FakeSessionRecordingCrawler):
    """Same flat fan-out as `_FakeSessionRecordingCrawler`, plus a
    `close_session` that records every call, to prove a long-lived worker
    tab gets closed and rebuilt every `session_recycle_after` visits
    instead of accumulating JS heap/listeners for the whole crawl
    (confirmed live on austral.edu.ar: a tab kept navigating through 50
    real pages without ever closing grew from ~9MB/~90 JS event listeners
    to ~700MB/~11000 listeners, with V8's own garbage-collection pauses
    landing squarely on the slowest FETCH timings observed)."""

    def __init__(self, n_pages: int) -> None:
        super().__init__(n_pages)
        self.closed_session_ids: List[str] = []

    async def close_session(self, session_id: str) -> None:
        self.closed_session_ids.append(session_id)


def test_session_recycled_every_configured_number_of_visits():
    fake = _FakeSessionRecyclingCrawler(n_pages=8)
    mech = MechanicalCrawler(
        fake, config=MechanicalCrawlerConfig(page_concurrency=1, session_recycle_after=3)
    )
    asyncio.run(mech.crawl_site(fake.root_url))

    # 1 root + 8 leaves = 9 visits, recycled every 3rd -> exactly 3 closes.
    assert len(fake.closed_session_ids) == 3
    assert fake.closed_session_ids == ["worker-0"] * 3


def test_session_never_recycled_when_disabled():
    fake = _FakeSessionRecyclingCrawler(n_pages=8)
    mech = MechanicalCrawler(
        fake, config=MechanicalCrawlerConfig(page_concurrency=1, session_recycle_after=None)
    )
    asyncio.run(mech.crawl_site(fake.root_url))

    assert fake.closed_session_ids == []


class _FakeOneBlockedPageCrawler:
    """Three pages: the middle one always raises (an anti-bot block, a
    timeout, any `discover_page` failure) - the other two must still get
    visited normally. Reproduces a real hang seen live on austral.edu.ar:
    a single page 200+ into a crawl failed discovery ("Structural: no
    <body> tag"), and with nothing catching that exception the one worker
    (`page_concurrency=1`, the default) died mid-loop - every URL still
    queued behind it, including ones already enqueued by pages visited
    earlier, then sat forever, since `_url_frontier.join()` waits for a
    `task_done()` no live worker was left to ever call."""

    def __init__(self) -> None:
        self.url_a = "http://fixture/a"
        self.blocked_url = "http://fixture/blocked"
        self.url_c = "http://fixture/c"
        self.discover_calls: List[str] = []

    async def discover_page(self, url: str, session_id=None) -> PageState:
        self.discover_calls.append(url)
        if url == self.blocked_url:
            raise RuntimeError("crawl4ai navigation failed: Blocked by anti-bot protection")
        if url == self.url_a:
            links = [{"href": self.blocked_url, "scheme": "http"}, {"href": self.url_c, "scheme": "http"}]
            return PageState(url=self.url_a, links=links)
        return PageState(url=url)

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        raise AssertionError("fixture has no components to click")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("not exercised by this fixture")


def test_one_blocked_page_does_not_hang_the_rest_of_the_crawl():
    fake = _FakeOneBlockedPageCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig())

    # A crawl that actually hangs would make this call itself hang - the
    # real symptom is "no advance at all", not a clean failure - so simply
    # returning here (asyncio.run has no timeout of its own) already
    # proves the fix; the assertions below confirm *what* came back.
    results = asyncio.run(mech.crawl_site(fake.url_a))

    visited_urls = {r.url for r in results}
    assert fake.url_a in fake.discover_calls
    assert fake.blocked_url in fake.discover_calls
    assert fake.url_c in fake.discover_calls
    # The blocked page is recorded as a failure, not silently dropped...
    assert any(e.action == "discover" and e.page_url == route_shape(fake.blocked_url) for e in mech.errors)
    # ...and, critically, is not retried forever - the frontier still
    # drains and the crawl still returns.
    assert route_shape(fake.url_c) in visited_urls
