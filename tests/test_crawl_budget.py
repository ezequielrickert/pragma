"""One run's budget: how much it does before stopping and handing over.

The point of the design is that there is no "incremental mode" - an
unlimited budget is the same code path with `None` in it, so a long run and
a series of short ones cannot drift apart.
"""
import asyncio
import time
from typing import List

import pytest

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import (
    BudgetTracker,
    CrawlBudget,
    MechanicalCrawler,
    MechanicalCrawlerConfig,
)
from utils.urls import route_shape

SITE = "shop.example"
START = "http://shop.example/p0"


class _FlakyFirstPageCrawler:
    """p0's own interactive components always fail once (an anti-bot block,
    a stale session, ...) - the retried visit then has nothing left to
    interact with (each failed path is marked interacted, never retried
    forever) and finishes normally. p0 links to p1, which has no components
    of its own and finishes on its first visit.
    """

    def __init__(self) -> None:
        self.discover_calls: List[str] = []

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        self.discover_calls.append(url)
        if url == START:
            components = [
                {"path": f"#btn{i}", "tag": "button", "text": f"btn{i}", "visible": True}
                for i in range(3)
            ]
            links = [{"href": "http://shop.example/p1", "text": "next", "scheme": "http"}]
            return PageState(url=url, components=components, links=links)
        return PageState(url=url, components=[], links=[])

    async def click(self, url: str, session_id: str, path: str) -> PageState:
        raise RuntimeError("blocked by anti-bot protection")

    async def resync(self, url: str, session_id: str = "") -> PageState:
        # Same url as what's being checked against - tells
        # check_for_silent_navigation this wasn't a silent navigation, so
        # the 3-strike circuit breaker (not the silent-nav path) is what
        # ends up setting interrupted_by_navigation.
        return PageState(url=url, components=[], links=[])

    async def close_session(self, session_id: str) -> None:
        return None


class _AlwaysBlockedCrawler:
    """Every visit of this url gets a fresh set of components - distinct
    `path` *and* `text` (Frontier.eligible excludes by content identity,
    tag/role/name/form/text, once a failed click marks it - a same-text
    "retry" component would stay excluded forever after the first failure,
    same as a real re-rendered DOM would) - and every click fails.
    Simulates a page that reliably trips the circuit breaker on every
    single attempt and never finishes on its own.
    """

    def __init__(self) -> None:
        self.discover_calls: List[str] = []
        self._visit_index = 0

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        self.discover_calls.append(url)
        self._visit_index += 1
        components = [
            {
                "path": f"#btn{self._visit_index}-{i}", "tag": "button",
                "text": f"btn{self._visit_index}-{i}", "visible": True,
            }
            for i in range(3)
        ]
        return PageState(url=url, components=components, links=[])

    async def click(self, url: str, session_id: str, path: str) -> PageState:
        raise RuntimeError("blocked by anti-bot protection")

    async def resync(self, url: str, session_id: str = "") -> PageState:
        return PageState(url=url, components=[], links=[])

    async def close_session(self, session_id: str) -> None:
        return None


class _LinkChainCrawler:
    """Every page links to the next, so the frontier never runs dry on its
    own - anything that stops the crawl here is the budget."""

    def __init__(self, length: int = 25) -> None:
        self.length = length
        self.fetched: List[str] = []

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        self.fetched.append(url)
        index = int(url.rsplit("/p", 1)[1])
        links = []
        if index + 1 < self.length:
            links = [{"href": f"http://shop.example/p{index + 1}", "text": "next", "scheme": "http"}]
        return PageState(url=url, components=[], links=links)

    async def close_session(self, session_id: str) -> None:
        return None


def _crawl(budget: CrawlBudget) -> _LinkChainCrawler:
    store = LadybugGraphStore(SITE)
    store.connect()
    crawler = _LinkChainCrawler()
    mech = MechanicalCrawler(
        crawler,
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, base_url=START),
            base_url=START,
            budget=budget,
            page_concurrency=1,
        ),
    )
    asyncio.run(mech.crawl_site(START))
    crawler.stopped_reason = mech.stopped_reason
    return crawler


def test_an_empty_budget_is_not_a_budget():
    assert CrawlBudget().is_unlimited()
    assert not CrawlBudget(pages=5).is_unlimited()


def test_page_budget_stops_the_run_early():
    crawler = _crawl(CrawlBudget(pages=5))

    assert len(crawler.fetched) == 5
    assert "page budget" in crawler.stopped_reason


def test_an_unlimited_budget_drains_the_whole_frontier():
    """The long run is the same path with None in it, not a second mode."""
    crawler = _crawl(CrawlBudget())

    assert len(crawler.fetched) == 25
    assert crawler.stopped_reason is None


def test_node_budget_counts_what_the_pages_contained():
    """Each page here contributes itself plus one link, so a node budget
    trips at roughly half the page count a page budget would."""
    crawler = _crawl(CrawlBudget(nodes=8))

    assert 0 < len(crawler.fetched) < 25
    assert "node budget" in crawler.stopped_reason


def test_pages_are_reported_before_nodes_when_both_trip():
    """Declaration order decides, so the operator sees the cap they most
    likely set on purpose."""
    tracker = BudgetTracker(CrawlBudget(pages=1, nodes=1))
    tracker.record_page()
    tracker.record_nodes(5)

    assert "page budget" in tracker.exhausted_reason()


def test_time_budget_trips_without_any_page_finishing():
    """The case pages and nodes cannot cover: since the per-page ceiling was
    removed, a page stuck in its own reveal loop ends no page and creates no
    node, so only wall clock still fires."""
    tracker = BudgetTracker(CrawlBudget(minutes=0.0001))
    time.sleep(0.02)

    assert tracker.pages == 0
    assert "time budget" in tracker.exhausted_reason()


def test_nothing_is_exhausted_while_there_is_room():
    tracker = BudgetTracker(CrawlBudget(pages=10, nodes=100, minutes=60))
    tracker.record_page()
    tracker.record_nodes(3)

    assert tracker.exhausted_reason() is None


def test_a_requeued_interrupted_visit_does_not_spend_the_page_budget():
    """CrawlBudget.pages counts pages FINISHED this run (its own docstring) -
    an interrupted pass that gets requeued has not finished and must not
    spend it. p0's own first attempt gets interrupted and requeued; p1 (which
    p0 linked to before its own requeue) is what actually finishes and
    rightly spends the one page-budget slot. Before this was fixed, p0's
    interrupted attempt would have tripped a pages=1 budget immediately,
    and p1 - real, available, already-discovered work - would never have
    been attempted at all.
    """
    store = LadybugGraphStore(SITE)
    store.connect()
    crawler = _FlakyFirstPageCrawler()
    mech = MechanicalCrawler(
        crawler,
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, base_url=START),
            base_url=START,
            budget=CrawlBudget(pages=1),
            page_concurrency=1,
        ),
    )
    asyncio.run(mech.crawl_site(START))

    # p0's interrupted attempt spent nothing; p1 is what spent the one slot.
    assert crawler.discover_calls == [START, "http://shop.example/p1"]
    assert mech._unique_visits == 1
    assert mech._requeued_visits == 1
    assert mech.stopped_reason is not None
    assert "page budget" in mech.stopped_reason
    # The budget tripped right after p1 finished, before p0's requeued
    # attempt (already sitting in the queue) got a second try.
    assert crawler.discover_calls.count(START) == 1


def test_a_page_that_never_stops_failing_is_given_up_on_not_retried_forever():
    """UrlFrontier.requeue caps retries at max_requeue_attempts - past that,
    the page is marked Failed instead of cycling through the queue forever.
    Without a cap, a reliably-blocked page (or a popular redirect
    destination many different interrupted passes all land on) requeues
    itself without bound - the crawl's own "requeued" count climbing far
    past "unique" and the queue growing without limit.
    """
    store = LadybugGraphStore(SITE)
    store.connect()
    crawler = _AlwaysBlockedCrawler()
    mech = MechanicalCrawler(
        crawler,
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, base_url=START),
            base_url=START,
            page_concurrency=1,
            max_requeue_attempts=2,
        ),
    )
    asyncio.run(mech.crawl_site(START))

    # 1 initial attempt + 2 allowed retries = 3 total discover_page calls,
    # then the crawl gives up instead of continuing forever.
    assert len(crawler.discover_calls) == 3
    assert mech._unique_visits == 0
    assert mech._requeued_visits == 3
    assert mech._gave_up_visits == 1
    # Marked concluded, not left Pending for a resumed run to retry forever -
    # is_visited/upsert_page are keyed by route_shape, not the literal url.
    assert store.is_visited(route_shape(START))
    assert not store.get_pending()


@pytest.mark.parametrize("budget", [CrawlBudget(pages=3), CrawlBudget(nodes=4)])
def test_a_cut_run_leaves_the_rest_pending(budget):
    """What is left behind is what the next run resumes from - the queue is
    drained without visiting so crawl_site's join() still returns."""
    store = LadybugGraphStore(SITE)
    store.connect()
    mech = MechanicalCrawler(
        _LinkChainCrawler(),
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, base_url=START),
            base_url=START,
            budget=budget,
            page_concurrency=1,
        ),
    )
    asyncio.run(mech.crawl_site(START))

    assert mech.stopped_reason is not None
    assert store.get_pending(), "a cut run must leave resumable work behind"
