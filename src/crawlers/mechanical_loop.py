"""The mechanical, exhaustive-but-bounded interaction loop over a site.
Details: docs/dev/crawlers/mechanical_loop.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from ..utils.urls import clean_url, is_in_scope, route_shape
from .crawl4ai_crawler import Crawl4AICrawler
from .fill_values import default_placeholder_fill_value
from .graph_sink import GraphStoreInteractionTracker, GraphStoreSink
from .interaction_tracker import InMemoryInteractionTracker, InteractionTracker
from .page_visitor import PageVisitor
from .visit_result import ComponentInteraction, PageVisitResult


@dataclass
class MechanicalCrawlerConfig:
    """Every tuning knob `MechanicalCrawler` accepts beyond `crawler`/`tracker`.
    Details: docs/dev/crawlers/mechanical_loop.md#mechanicalcrawlerconfig
    """

    element_budget: int = 200
    fill_value_fn: Callable[[Dict[str, Any], str], Awaitable[str]] = default_placeholder_fill_value
    max_pages: Optional[int] = None
    sink: Optional[GraphStoreSink] = None
    max_passes_per_page: int = 10
    max_visits_per_route_shape: int = 1
    page_concurrency: int = 1
    state_transition_overlap_threshold: float = 0.5
    base_url: Optional[str] = None
    allow_subdomains: bool = False


class MechanicalCrawler:
    """Drives `Crawl4AICrawler` through a full site crawl; owns the URL frontier only.
    Details: docs/dev/crawlers/mechanical_loop.md#mechanicalcrawler
    """

    def __init__(
        self,
        crawler: Crawl4AICrawler,
        tracker: Optional[InteractionTracker] = None,
        config: Optional[MechanicalCrawlerConfig] = None,
    ) -> None:
        config = config or MechanicalCrawlerConfig()
        self.crawler = crawler
        self.page_concurrency = max(1, config.page_concurrency)
        self.max_pages = config.max_pages
        self.max_visits_per_route_shape = config.max_visits_per_route_shape
        self.base_url = config.base_url
        self.allow_subdomains = config.allow_subdomains
        self.sink = config.sink
        # A sink almost always implies its matching GraphStore tracker.
        # Details: docs/dev/crawlers/mechanical_loop.md#tracker-default
        if tracker is not None:
            self.tracker = tracker
        elif config.sink is not None:
            self.tracker = GraphStoreInteractionTracker(config.sink.graph_store, config.sink.site)
        else:
            self.tracker = InMemoryInteractionTracker()

        # Queue, not deque - workers await new items; .join() detects "done".
        # Details: docs/dev/crawlers/mechanical_loop.md#url_frontier
        self._url_frontier: "asyncio.Queue[str]" = asyncio.Queue()
        self._queued: Set[str] = set()  # clean_url keys already enqueued or visited, dedup guard
        # Narrower than _queued - guards a same-destination-redirect race.
        # Details: docs/dev/crawlers/mechanical_loop.md#in_flight
        self._in_flight: Set[str] = set()
        self._route_shape_visits: Dict[str, int] = {}  # route_shape() key -> completed-visit count
        self.page_results: List[PageVisitResult] = []
        self._pages_visited = 0
        self._page_visitor = PageVisitor(crawler, self.tracker, self._enqueue, self._enqueue_links, config)

    @property
    def errors(self) -> List[ComponentInteraction]:
        """Every failed interaction so far; delegates to `PageVisitor`.
        Details: docs/dev/crawlers/mechanical_loop.md#errors
        """
        return self._page_visitor.errors

    def _enqueue(self, url: str) -> None:
        key = clean_url(url)
        if key in self._queued or self.tracker.is_visited(key):
            return
        # Single scope choke-point for every discovered/navigated-to URL.
        # Details: docs/dev/crawlers/mechanical_loop.md#_enqueue-scope-gate
        if self.base_url and not is_in_scope(url, self.base_url, self.allow_subdomains):
            return
        shape = route_shape(url)
        visits = self._route_shape_visits.get(shape, 0)
        if visits >= self.max_visits_per_route_shape:
            print(
                f"Route shape {shape!r} already sampled {visits}x, skipping {url} "
                "to avoid unbounded session-token growth."
            )
            return
        self._queued.add(key)
        self._url_frontier.put_nowait(url)

    def _enqueue_links(self, links: List[Dict[str, str]]) -> None:
        """Queue every http(s) href; idempotent via `_enqueue`'s dedup guard.
        Details: docs/dev/crawlers/mechanical_loop.md#_enqueue_links
        """
        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - nothing to navigate to
            if href:
                self._enqueue(href)

    async def crawl_site(self, start_url: str) -> List[PageVisitResult]:
        """Crawl every page reachable from `start_url`, `page_concurrency` at a time.
        Details: docs/dev/crawlers/mechanical_loop.md#crawl_site
        """
        if self.base_url is None:
            self.base_url = start_url
        self._enqueue(start_url)
        workers = [asyncio.create_task(self._worker()) for _ in range(self.page_concurrency)]
        await self._url_frontier.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        return self.page_results

    async def _worker(self) -> None:
        """One concurrent visitor: pulls a URL, hands it to `PageVisitor`, requeues.
        Details: docs/dev/crawlers/mechanical_loop.md#_worker
        """
        while True:
            url = await self._url_frontier.get()
            try:
                if self.max_pages is not None and self._pages_visited >= self.max_pages:
                    continue  # cap reached - drain without visiting, see doc for soft-bound caveat
                key = clean_url(url)
                if self.tracker.is_visited(key):
                    continue
                if key in self._in_flight:
                    continue  # duplicate dequeue - see docs/dev/.../mechanical_loop.md#in_flight
                self._in_flight.add(key)
                try:
                    result = await self._page_visitor.visit(url)
                finally:
                    self._in_flight.discard(key)
                self.page_results.append(result)
                self._pages_visited += 1
                if result.interrupted_by_navigation:
                    # Requeue resolved_url directly - see doc for the redirect bug this avoids.
                    # Details: docs/dev/crawlers/mechanical_loop.md#_worker-requeue
                    self._url_frontier.put_nowait(result.resolved_url)
                else:
                    self.tracker.mark_visited(key)
                    shape = route_shape(url)
                    self._route_shape_visits[shape] = self._route_shape_visits.get(shape, 0) + 1
            finally:
                self._url_frontier.task_done()
