"""The mechanical, exhaustive-but-bounded interaction loop over a site.
Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#module
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from utils.urls import clean_url
from ...browser.crawl4ai_crawler import Crawl4AICrawler
from ..graph_sink import GraphStoreInteractionTracker
from ..interaction_tracker import InMemoryInteractionTracker, InteractionTracker
from ..page_visitor import PageVisitor
from ..visit_result import ComponentInteraction, PageVisitResult
from .config import MechanicalCrawlerConfig
from .frontier import UrlFrontier
from .worker_pacing import WorkerPacing


class MechanicalCrawler:
    """Drives `Crawl4AICrawler` through a full site crawl; owns the URL
    frontier only.
    Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#mechanicalcrawler
    """

    def __init__(
        self,
        crawler: Crawl4AICrawler,
        tracker: Optional[InteractionTracker] = None,
        config: Optional[MechanicalCrawlerConfig] = None,
    ) -> None:
        config = config or MechanicalCrawlerConfig()
        self.crawler = crawler
        self.max_pages = config.max_pages
        self.session_recycle_after = config.session_recycle_after
        self.sink = config.sink
        # A sink almost always implies its matching GraphStore tracker.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#tracker-default
        if tracker is not None:
            self.tracker = tracker
        elif config.sink is not None:
            self.tracker = GraphStoreInteractionTracker(config.sink.graph_store, config.sink.site)
        else:
            self.tracker = InMemoryInteractionTracker()

        # Collaborators - see each module's own docstring for why it's
        # split out. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#__init__-collaborators
        self._frontier = UrlFrontier(self.tracker, config)
        self._pacing = WorkerPacing(crawler, config)
        self.page_results: List[PageVisitResult] = []
        self._pages_visited = 0
        self._page_visitor = PageVisitor(
            crawler, self.tracker, self._frontier.enqueue, self._frontier.enqueue_links, config
        )

    @property
    def errors(self) -> List[ComponentInteraction]:
        """Every failed interaction so far; delegates to `PageVisitor`.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#errors
        """
        return self._page_visitor.errors

    async def crawl_site(self, start_url: str) -> List[PageVisitResult]:
        """Crawl every page reachable from `start_url`, `page_concurrency` at a time.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site
        """
        if self._frontier.base_url is None:
            self._frontier.base_url = start_url
        self._frontier.enqueue(start_url)
        workers = [asyncio.create_task(self._worker(i)) for i in range(self._pacing.page_concurrency)]
        await self._frontier.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        return self.page_results

    async def _recycle_session_if_due(self, browser_session_id: str, visits_since_recycle: int) -> int:
        """Close `browser_session_id`'s tab once it's carried `session_recycle_after`
        visits, so crawl4ai rebuilds a fresh one on the worker's next visit.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_recycle_session_if_due
        """
        if self.session_recycle_after is None or visits_since_recycle < self.session_recycle_after:
            return visits_since_recycle
        close = getattr(self.crawler, "close_session", None)
        if close is not None:
            try:
                await close(browser_session_id)
            except Exception as exc:
                print(f"Warning: could not recycle session {browser_session_id!r}: {exc}")
        return 0

    async def _worker(self, worker_id: int) -> None:
        """One concurrent visitor: pulls a URL, hands it to `PageVisitor`, requeues.
        Reuses one browser tab (keyed by `worker_id`) across every URL it
        visits, so tab count stays at `page_concurrency` for the whole crawl
        instead of growing by one per page - periodically recycled, see
        `_recycle_session_if_due`. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker
        """
        browser_session_id = f"worker-{worker_id}"
        visits_since_recycle = 0
        while True:
            await self._pacing.wait_for_memory_headroom()
            await self._pacing.wait_for_capacity(worker_id)
            url = await self._frontier.get()
            try:
                if self.max_pages is not None and self._pages_visited >= self.max_pages:
                    continue  # cap reached - drain without visiting, see doc for soft-bound caveat
                key = clean_url(url)
                if self.tracker.is_visited(key):
                    continue
                if self._frontier.is_in_flight(key):
                    continue  # duplicate dequeue - see docs/dev/.../mechanical_loop/frontier.md#in_flight
                self._frontier.mark_in_flight(key)
                try:
                    result = await self._page_visitor.visit(url, browser_session_id)
                finally:
                    self._frontier.clear_in_flight(key)
                visits_since_recycle += 1
                visits_since_recycle = await self._recycle_session_if_due(browser_session_id, visits_since_recycle)
                self.page_results.append(result)
                self._pages_visited += 1
                if result.interrupted_by_navigation:
                    # Requeue resolved_url directly - see doc for the redirect bug this avoids.
                    # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-requeue
                    self._frontier.requeue(result.resolved_url)
                else:
                    self.tracker.mark_visited(key)
                    self._frontier.record_route_shape_visit(url)
            finally:
                self._frontier.task_done()
