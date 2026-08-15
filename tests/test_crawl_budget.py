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
from database.memory_graph_store import InMemoryGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import (
    BudgetTracker,
    CrawlBudget,
    MechanicalCrawler,
    MechanicalCrawlerConfig,
)

SITE = "shop.example"
START = "http://shop.example/p0"


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
    store = InMemoryGraphStore()
    store.connect()
    crawler = _LinkChainCrawler()
    mech = MechanicalCrawler(
        crawler,
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, SITE, base_url=START),
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


@pytest.mark.parametrize("budget", [CrawlBudget(pages=3), CrawlBudget(nodes=4)])
def test_a_cut_run_leaves_the_rest_pending(budget):
    """What is left behind is what the next run resumes from - the queue is
    drained without visiting so crawl_site's join() still returns."""
    store = InMemoryGraphStore()
    store.connect()
    mech = MechanicalCrawler(
        _LinkChainCrawler(),
        config=MechanicalCrawlerConfig(
            sink=GraphStoreSink(store, SITE, base_url=START),
            base_url=START,
            budget=budget,
            page_concurrency=1,
        ),
    )
    asyncio.run(mech.crawl_site(START))

    assert mech.stopped_reason is not None
    assert store.get_pending(SITE), "a cut run must leave resumable work behind"
