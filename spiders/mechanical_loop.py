"""The mechanical, exhaustive-but-bounded interaction loop over a site.
Details: docs/dev/spiders/mechanical_loop.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union

import psutil

from utils.urls import clean_url, is_in_scope, route_shape
from .crawl4ai_crawler import Crawl4AICrawler
from .crawl4ai_crawler_pool import Crawl4AICrawlerPool
from .fill_values import default_placeholder_fill_value
from .graph_sink import GraphStoreInteractionTracker, GraphStoreSink
from .interaction_tracker import InMemoryInteractionTracker, InteractionTracker
from .page_visitor import PageVisitor
from .visit_result import ComponentInteraction, PageVisitResult

# _wait_for_memory_headroom's poll interval while blocked.
# Details: docs/dev/spiders/mechanical_loop.md#_memory_check_interval_seconds
_MEMORY_CHECK_INTERVAL_SECONDS = 2.0

# Give up waiting and proceed anyway past this many seconds under the
# ceiling, so a machine whose memory pressure has nothing to do with this
# crawl (or stays permanently loaded) can't stall it forever.
# Details: docs/dev/spiders/mechanical_loop.md#_memory_wait_timeout_seconds
_MEMORY_WAIT_TIMEOUT_SECONDS = 300.0

# _wait_for_target_capacity's poll interval while a worker is over budget.
# Details: docs/dev/spiders/mechanical_loop.md#_target_health_check_interval_seconds
_TARGET_HEALTH_CHECK_INTERVAL_SECONDS = 1.0


@dataclass
class MechanicalCrawlerConfig:
    """Every tuning knob `MechanicalCrawler` accepts beyond `crawler`/`tracker`.
    Details: docs/dev/spiders/mechanical_loop.md#mechanicalcrawlerconfig
    """

    element_budget: int = 200
    fill_value_fn: Callable[[Dict[str, Any], str], Awaitable[str]] = default_placeholder_fill_value
    max_pages: Optional[int] = None
    sink: Optional[GraphStoreSink] = None
    max_passes_per_page: int = 10
    max_visits_per_route_shape: int = 1
    # See PragmaConfig.page_concurrency for why this default isn't 1 anymore.
    page_concurrency: int = 4
    state_transition_overlap_threshold: float = 0.5
    base_url: Optional[str] = None
    allow_subdomains: bool = False
    # Visits per worker tab before it's closed and rebuilt from scratch.
    # Details: docs/dev/spiders/mechanical_loop.md#session_recycle_after
    session_recycle_after: Optional[int] = 15
    # System-memory-used percent above which a worker pauses picking up its
    # next page - what makes raising page_concurrency safe rather than just
    # a faster way to reproduce the same OOM. `None` disables the check.
    # Details: docs/dev/spiders/mechanical_loop.md#memory_ceiling_percent
    memory_ceiling_percent: Optional[float] = 85.0
    # Effective worker count never drops below this even under severe target
    # strain - see _effective_concurrency.
    # Details: docs/dev/spiders/mechanical_loop.md#min_page_concurrency
    min_page_concurrency: int = 1
    # crawler.target_slowdown_ratio range over which effective concurrency
    # linearly tapers from page_concurrency down to min_page_concurrency -
    # below the start ratio, full concurrency; at/above the end ratio, the
    # floor. Details: docs/dev/spiders/mechanical_loop.md#concurrency_taper
    concurrency_taper_start_ratio: float = 2.0
    concurrency_taper_end_ratio: float = 4.0


class MechanicalCrawler:
    """Drives `Crawl4AICrawler` (or a `Crawl4AICrawlerPool`) through a full
    site crawl; owns the URL frontier only.
    Details: docs/dev/spiders/mechanical_loop.md#mechanicalcrawler
    """

    def __init__(
        self,
        crawler: Union[Crawl4AICrawler, Crawl4AICrawlerPool],
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
        self.session_recycle_after = config.session_recycle_after
        self.memory_ceiling_percent = config.memory_ceiling_percent
        self.min_page_concurrency = max(1, min(config.min_page_concurrency, self.page_concurrency))
        self.concurrency_taper_start_ratio = config.concurrency_taper_start_ratio
        self.concurrency_taper_end_ratio = config.concurrency_taper_end_ratio
        self.sink = config.sink
        # A sink almost always implies its matching GraphStore tracker.
        # Details: docs/dev/spiders/mechanical_loop.md#tracker-default
        if tracker is not None:
            self.tracker = tracker
        elif config.sink is not None:
            self.tracker = GraphStoreInteractionTracker(config.sink.graph_store, config.sink.site)
        else:
            self.tracker = InMemoryInteractionTracker()

        # Queue, not deque - workers await new items; .join() detects "done".
        # Details: docs/dev/spiders/mechanical_loop.md#url_frontier
        self._url_frontier: "asyncio.Queue[str]" = asyncio.Queue()
        self._queued: Set[str] = set()  # clean_url keys already enqueued or visited, dedup guard
        # Narrower than _queued - guards a same-destination-redirect race.
        # Details: docs/dev/spiders/mechanical_loop.md#in_flight
        self._in_flight: Set[str] = set()
        self._route_shape_visits: Dict[str, int] = {}  # route_shape() key -> completed-visit count
        self.page_results: List[PageVisitResult] = []
        self._pages_visited = 0
        self._page_visitor = PageVisitor(crawler, self.tracker, self._enqueue, self._enqueue_links, config)

    @property
    def errors(self) -> List[ComponentInteraction]:
        """Every failed interaction so far; delegates to `PageVisitor`.
        Details: docs/dev/spiders/mechanical_loop.md#errors
        """
        return self._page_visitor.errors

    def _enqueue(self, url: str) -> None:
        key = clean_url(url)
        if key in self._queued or self.tracker.is_visited(key):
            return
        # Single scope choke-point for every discovered/navigated-to URL.
        # Details: docs/dev/spiders/mechanical_loop.md#_enqueue-scope-gate
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
        Details: docs/dev/spiders/mechanical_loop.md#_enqueue_links
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
        Details: docs/dev/spiders/mechanical_loop.md#crawl_site
        """
        if self.base_url is None:
            self.base_url = start_url
        self._enqueue(start_url)
        workers = [asyncio.create_task(self._worker(i)) for i in range(self.page_concurrency)]
        await self._url_frontier.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        return self.page_results

    async def _recycle_session_if_due(self, browser_session_id: str, visits_since_recycle: int) -> int:
        """Close `browser_session_id`'s tab once it's carried `session_recycle_after`
        visits, so crawl4ai rebuilds a fresh one on the worker's next visit.
        Details: docs/dev/spiders/mechanical_loop.md#_recycle_session_if_due
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

    async def _wait_for_memory_headroom(self) -> None:
        """Block this worker from picking up its next page while system
        memory is over `memory_ceiling_percent` used. A crawl with several
        concurrent Chromium tabs can genuinely run the machine out of memory;
        this is what lets `page_concurrency` be raised without just hitting
        that ceiling faster. Details: docs/dev/spiders/mechanical_loop.md#_wait_for_memory_headroom
        """
        if self.memory_ceiling_percent is None:
            return
        waited_seconds = 0.0
        while psutil.virtual_memory().percent >= self.memory_ceiling_percent:
            if waited_seconds >= _MEMORY_WAIT_TIMEOUT_SECONDS:
                print(
                    f"Warning: system memory still >= {self.memory_ceiling_percent}% used after "
                    f"{_MEMORY_WAIT_TIMEOUT_SECONDS:.0f}s - proceeding anyway rather than stall forever."
                )
                return
            await asyncio.sleep(_MEMORY_CHECK_INTERVAL_SECONDS)
            waited_seconds += _MEMORY_CHECK_INTERVAL_SECONDS

    def _effective_concurrency(self) -> int:
        """How many workers should be actively fetching right now, tapered
        down from `page_concurrency` toward `min_page_concurrency` as
        `crawler.target_slowdown_ratio` worsens - fewer simultaneous
        in-flight requests against a target that's already straining, not
        just slower per-request pacing (that's `Crawl4AICrawler`'s own
        backoff). Reads a plain attribute crawl4ai_crawler.py updates every
        navigation; missing entirely (e.g. a fake crawler in a test) reads
        as "healthy", not as degraded.
        Details: docs/dev/spiders/mechanical_loop.md#_effective_concurrency
        """
        ratio = getattr(self.crawler, "target_slowdown_ratio", 1.0)
        if ratio <= self.concurrency_taper_start_ratio:
            return self.page_concurrency
        if ratio >= self.concurrency_taper_end_ratio:
            return self.min_page_concurrency
        taper_span = self.concurrency_taper_end_ratio - self.concurrency_taper_start_ratio
        fraction_degraded = (ratio - self.concurrency_taper_start_ratio) / taper_span
        reduction = round(fraction_degraded * (self.page_concurrency - self.min_page_concurrency))
        return max(self.min_page_concurrency, self.page_concurrency - reduction)

    async def _wait_for_target_capacity(self, worker_id: int) -> None:
        """Block this worker while its id is outside the currently allowed
        concurrency budget (see `_effective_concurrency`). `min_page_concurrency`
        defaults to 1, so worker 0 always qualifies and the crawl can never
        fully stall here - only higher-numbered workers ever wait, and only
        for as long as the target stays degraded.
        Details: docs/dev/spiders/mechanical_loop.md#_wait_for_target_capacity
        """
        while worker_id >= self._effective_concurrency():
            await asyncio.sleep(_TARGET_HEALTH_CHECK_INTERVAL_SECONDS)

    async def _worker(self, worker_id: int) -> None:
        """One concurrent visitor: pulls a URL, hands it to `PageVisitor`, requeues.
        Reuses one browser tab (keyed by `worker_id`) across every URL it
        visits, so tab count stays at `page_concurrency` for the whole crawl
        instead of growing by one per page - periodically recycled, see
        `_recycle_session_if_due`. Details: docs/dev/spiders/mechanical_loop.md#_worker
        """
        browser_session_id = f"worker-{worker_id}"
        visits_since_recycle = 0
        while True:
            await self._wait_for_memory_headroom()
            await self._wait_for_target_capacity(worker_id)
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
                    result = await self._page_visitor.visit(url, browser_session_id)
                finally:
                    self._in_flight.discard(key)
                visits_since_recycle += 1
                visits_since_recycle = await self._recycle_session_if_due(browser_session_id, visits_since_recycle)
                self.page_results.append(result)
                self._pages_visited += 1
                if result.interrupted_by_navigation:
                    # Requeue resolved_url directly - see doc for the redirect bug this avoids.
                    # Details: docs/dev/spiders/mechanical_loop.md#_worker-requeue
                    self._url_frontier.put_nowait(result.resolved_url)
                else:
                    self.tracker.mark_visited(key)
                    shape = route_shape(url)
                    self._route_shape_visits[shape] = self._route_shape_visits.get(shape, 0) + 1
            finally:
                self._url_frontier.task_done()
