"""Regression coverage for `PragmaBestFirstStrategy`
(spiders/orchestration/best_first_strategy.py) - issue #247: crawl4ai's
native `BestFirstCrawlingStrategy` carrying `PragmaFrontierMixin`'s
frontier rules and fixing the session_id bug (issue #246) for best-first
ordering. Frontier-rule behavior itself (scope gate, route-shape cap,
clean_url dedup) is already covered against `PragmaDeepCrawlStrategy` in
test_deep_crawl_strategy.py - `PragmaFrontierMixin` is shared code, not
duplicated here.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from crawl4ai import CrawlerRunConfig

from spiders.browser.crawl4ai_crawler.session_aware_dispatcher import SessionAwareDispatcher
from spiders.orchestration.best_first_strategy import PragmaBestFirstStrategy
from spiders.orchestration.route_shape_scorer import RouteShapeNoveltyScorer


@dataclass
class _FakeCrawlResult:
    url: str
    links: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    redirected_url: Optional[str] = None
    metadata: Optional[dict] = None
    success: bool = True


class _FakeCrawler:
    """Captures the `dispatcher=` kwarg `_arun_best_first` passes to
    `arun_many`, then hands back one fake result per requested URL - just
    enough to drive one iteration of the priority-queue loop."""

    def __init__(self) -> None:
        self.dispatcher_seen = None

    async def arun_many(self, urls, config, dispatcher=None):
        self.dispatcher_seen = dispatcher

        async def _stream():
            for url in urls:
                yield _FakeCrawlResult(url=url)

        return _stream()


def test_can_process_url_enforces_the_route_shape_cap():
    """Confirms PragmaFrontierMixin is actually mixed in, not just imported."""
    strategy = PragmaBestFirstStrategy(max_visits_per_route_shape=1)
    strategy._route_shape_visits["example.com/o/{token}"] = 1

    assert asyncio.run(strategy.can_process_url("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN", 1)) is False


def test_defaults_to_a_route_shape_novelty_scorer_reading_its_own_visit_counts():
    strategy = PragmaBestFirstStrategy(max_visits_per_route_shape=2)

    assert isinstance(strategy.url_scorer, RouteShapeNoveltyScorer)
    assert strategy.url_scorer.score("http://example.com/page") == 1.0

    strategy._route_shape_visits["example.com/page"] = 1
    assert strategy.url_scorer.score("http://example.com/page") == 0.5


def test_a_caller_supplied_url_scorer_is_kept_untouched():
    class _FixedScorer(RouteShapeNoveltyScorer):
        def _calculate_score(self, url: str) -> float:
            return 0.42

    custom = _FixedScorer(route_shape_visits={}, max_visits_per_route_shape=1)
    strategy = PragmaBestFirstStrategy(url_scorer=custom)

    assert strategy.url_scorer is custom


def test_arun_best_first_routes_arun_many_through_a_session_aware_dispatcher():
    """The bug PragmaBestFirstStrategy exists to avoid: crawl4ai's own
    BestFirstCrawlingStrategy._arun_best_first calls arun_many() with no
    dispatcher=, so it silently falls back to a bare MemoryAdaptiveDispatcher
    (the one that drops session_id - issue #246)."""
    strategy = PragmaBestFirstStrategy(max_pages=1)
    crawler = _FakeCrawler()

    async def _run():
        results = []
        async for result in strategy._arun_best_first(
            "http://example.com/start", crawler, CrawlerRunConfig()
        ):
            results.append(result)
        return results

    results = asyncio.run(_run())

    assert [r.url for r in results] == ["http://example.com/start"]
    assert isinstance(crawler.dispatcher_seen, SessionAwareDispatcher)
    # Same instance across the crawl, not rebuilt per batch.
    assert crawler.dispatcher_seen is strategy._dispatcher
