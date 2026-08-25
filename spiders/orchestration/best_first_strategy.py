"""`PragmaBestFirstStrategy`: crawl4ai's native `BestFirstCrawlingStrategy`
carrying `PragmaFrontierMixin`'s frontier rules (`deep_crawl_strategy.py`)
and fixing the `session_id` bug `SessionAwareDispatcher` targets
(issue #246) for best-first ordering. Not yet wired into `CrawlEngineCore`
- that's a separate ticket on the same map (issue #245).
Details: docs/dev/spiders/orchestration/best_first_strategy.md#module
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.models import CrawlResult
from crawl4ai.types import AsyncWebCrawler, CrawlerRunConfig

from spiders.browser.crawl4ai_crawler.session_aware_dispatcher import SessionAwareDispatcher
from spiders.orchestration.deep_crawl_strategy import PragmaFrontierMixin
from spiders.orchestration.route_shape_scorer import RouteShapeNoveltyScorer


class PragmaBestFirstStrategy(PragmaFrontierMixin, BestFirstCrawlingStrategy):
    """Same frontier rules as `PragmaDeepCrawlStrategy`, ordered by a
    `url_scorer` (see `spiders/orchestration/route_shape_scorer.py`)
    instead of level-by-level BFS. Also fixes the `session_id` bug
    `SessionAwareDispatcher` targets (issue #246): crawl4ai's own
    `BestFirstCrawlingStrategy._arun_best_first`
    (`crawl4ai/deep_crawling/bff_strategy.py`) calls `crawler.arun_many()`
    with no `dispatcher=` argument, so it always falls back to a bare
    `MemoryAdaptiveDispatcher` - the one with the dropped-`session_id` bug.
    `_arun_best_first` is the single place that call happens (both
    `_arun_batch` and `_arun_stream` just delegate to it), so overriding it
    alone - reproducing its body with one line changed - is enough; there's
    no need to also override `_arun_batch`/`_arun_stream` themselves.
    Details: docs/dev/spiders/orchestration/best_first_strategy.md#pragmabestfirststrategy
    """

    # Configurable batch size for draining the priority queue - crawl4ai's
    # own BestFirstCrawlingStrategy hard-codes this as a module constant;
    # kept identical here as this override reproduces its loop body.
    _BATCH_SIZE = 10

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.url_scorer is None:
            # Default to route-shape novelty, reading the same
            # _route_shape_visits PragmaFrontierMixin.__init__ just set up -
            # constructed here rather than accepted as a kwarg because it
            # needs a reference to this instance's own dict, which doesn't
            # exist until the base __init__ above has run. A caller that
            # passes its own url_scorer keeps it untouched.
            self.url_scorer = RouteShapeNoveltyScorer(self._route_shape_visits, self.max_visits_per_route_shape)
        # One dispatcher instance for the whole crawl, not one per batch -
        # matches how crawl4ai's own default dispatcher is scoped to a
        # single arun_many() call tree, and lets its memory/rate-limiting
        # state (see SessionAwareDispatcher's base, MemoryAdaptiveDispatcher)
        # persist across levels.
        self._dispatcher = SessionAwareDispatcher()

    async def _arun_best_first(
        self,
        start_url: str,
        crawler: AsyncWebCrawler,
        config: CrawlerRunConfig,
    ) -> AsyncGenerator[CrawlResult, None]:
        """Reproduces `BestFirstCrawlingStrategy._arun_best_first`
        unchanged except for passing `dispatcher=self._dispatcher` into the
        `arun_many()` call - see the class docstring for why overriding
        this one method is enough.
        Details: docs/dev/spiders/orchestration/best_first_strategy.md#_arun_best_first
        """
        self._cancel_event = asyncio.Event()

        queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

        if self._resume_state:
            visited = set(self._resume_state.get("visited", []))
            depths = dict(self._resume_state.get("depths", {}))
            self._pages_crawled = self._resume_state.get("pages_crawled", 0)
            queue_items = self._resume_state.get("queue_items", [])
            for item in queue_items:
                await queue.put((item["score"], item["depth"], item["url"], item["parent_url"]))
            if self._on_state_change:
                self._queue_shadow = [
                    (item["score"], item["depth"], item["url"], item["parent_url"])
                    for item in queue_items
                ]
        else:
            initial_score = self.url_scorer.score(start_url) if self.url_scorer else 0
            await queue.put((-initial_score, 0, start_url, None))
            visited: Set[str] = set()
            depths: Dict[str, int] = {start_url: 0}
            if self._on_state_change:
                self._queue_shadow = [(-initial_score, 0, start_url, None)]

        while not queue.empty() and not self._cancel_event.is_set():
            if self._pages_crawled >= self.max_pages:
                self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping crawl")
                break

            if await self._check_cancellation():
                self.logger.info("Crawl cancelled by user")
                break

            remaining = self.max_pages - self._pages_crawled
            batch_size = min(self._BATCH_SIZE, remaining)
            if batch_size <= 0:
                self.logger.info(f"Max pages limit ({self.max_pages}) reached, stopping crawl")
                break

            batch: List[Tuple[float, int, str, Optional[str]]] = []
            for _ in range(self._BATCH_SIZE):
                if queue.empty():
                    break
                item = await queue.get()
                if self._on_state_change and self._queue_shadow is not None:
                    try:
                        self._queue_shadow.remove(item)
                    except ValueError:
                        pass
                score, depth, url, parent_url = item
                if url in visited:
                    continue
                visited.add(url)
                batch.append(item)

            if not batch:
                continue

            urls = [item[2] for item in batch]
            batch_config = config.clone(deep_crawl_strategy=None, stream=True)
            stream_gen = await crawler.arun_many(urls=urls, config=batch_config, dispatcher=self._dispatcher)
            results_by_url: Dict[str, CrawlResult] = {}
            async for result in stream_gen:
                results_by_url[result.url] = result

            for score, depth, url, parent_url in batch:
                result = results_by_url.get(url)
                if result is None:
                    continue
                result.metadata = result.metadata or {}
                result.metadata["depth"] = depth
                result.metadata["parent_url"] = parent_url
                result.metadata["score"] = -score

                if result.success:
                    self._pages_crawled += 1

                yield result

                if result.success and self._pages_crawled >= self.max_pages:
                    self.logger.info(f"Max pages limit ({self.max_pages}) reached during batch, stopping crawl")
                    break

                if result.success:
                    new_links: List[Tuple[str, Optional[str]]] = []
                    await self.link_discovery(result, url, depth, visited, new_links, depths)

                    for new_url, new_parent in new_links:
                        new_depth = depths.get(new_url, depth + 1)
                        new_score = self.url_scorer.score(new_url) if self.url_scorer else 0
                        if new_score < self.score_threshold:
                            self.logger.debug(
                                f"URL {new_url} skipped: score {new_score} below threshold {self.score_threshold}"
                            )
                            self.stats.urls_skipped += 1
                            continue
                        queue_item = (-new_score, new_depth, new_url, new_parent)
                        await queue.put(queue_item)
                        if self._on_state_change and self._queue_shadow is not None:
                            self._queue_shadow.append(queue_item)

                    if self._on_state_change and self._queue_shadow is not None:
                        state = {
                            "strategy_type": "best_first",
                            "visited": list(visited),
                            "queue_items": [
                                {"score": s, "depth": d, "url": u, "parent_url": p}
                                for s, d, u, p in self._queue_shadow
                            ],
                            "depths": depths,
                            "pages_crawled": self._pages_crawled,
                            "cancelled": self._cancel_event.is_set(),
                        }
                        self._last_state = state
                        await self._on_state_change(state)

        if self._cancel_event.is_set() and self._on_state_change and self._queue_shadow is not None:
            state = {
                "strategy_type": "best_first",
                "visited": list(visited),
                "queue_items": [
                    {"score": s, "depth": d, "url": u, "parent_url": p}
                    for s, d, u, p in self._queue_shadow
                ],
                "depths": depths,
                "pages_crawled": self._pages_crawled,
                "cancelled": True,
            }
            self._last_state = state
            await self._on_state_change(state)
