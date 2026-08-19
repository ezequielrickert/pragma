"""The mechanical, exhaustive-but-bounded interaction loop over a site.
Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#module
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, List, Optional

from utils.urls import clean_url
from ...browser.crawl4ai_crawler import Crawl4AICrawler
from ..graph_sink import GraphStoreInteractionTracker
from ..interaction_tracker import InMemoryInteractionTracker, InteractionTracker
from ..page_visitor import PageVisitor
from ..visit_result import ComponentInteraction, PageVisitResult
from .budget import BudgetTracker
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
        # See MechanicalCrawlerConfig.two_phase_crawl for the full rationale.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_two_phase_crawl
        self._two_phase_crawl = config.two_phase_crawl
        self._scout_only = config.scout_only
        # See MechanicalCrawlerConfig.interact_only for the full rationale.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_interact_only
        self._interact_only = config.interact_only
        # A sink almost always implies its matching GraphStore tracker.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#tracker-default
        if tracker is not None:
            self.tracker = tracker
        elif config.sink is not None:
            self.tracker = GraphStoreInteractionTracker(config.sink.graph_store)
        else:
            self.tracker = InMemoryInteractionTracker()

        # Collaborators - see each module's own docstring for why it's
        # split out. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#__init__-collaborators
        self._frontier = UrlFrontier(self.tracker, config)
        self._pacing = WorkerPacing(crawler, config)
        self.page_results: List[PageVisitResult] = []
        self._pages_visited = 0
        # Split deliberately: a requeued visit prints exactly like a fresh one
        # in crawl4ai's own output, so a crawl churning on the same handful of
        # pages is indistinguishable from one making progress. Separating them
        # is the whole diagnostic value of the per-visit line.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#visit-counters
        self._unique_visits = 0
        self._requeued_visits = 0
        # A requeued visit UrlFrontier refused to retry again - past
        # max_requeue_attempts, marked Failed instead of cycling forever.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#visit-counters
        self._gave_up_visits = 0
        self._budget = BudgetTracker(config.budget)
        # Set once when a budget trips, then read by every other worker to
        # stop taking new pages. Also the "was this run partial" answer the
        # document pipeline needs afterwards.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#stopped_reason
        self.stopped_reason: Optional[str] = None
        self._page_visitor = PageVisitor(
            crawler, self.tracker, self._frontier.enqueue, self._frontier.enqueue_links,
            config, self._frontier.is_known
        )

    @property
    def errors(self) -> List[ComponentInteraction]:
        """Every failed interaction so far; delegates to `PageVisitor`.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#errors
        """
        return self._page_visitor.errors

    def _finished_route_shapes(self) -> List[str]:
        """Route shapes a previous run already sampled.

        Page keys in the graph are already route-shaped (`visit` derives
        `page_key` that way), so a Finished page's url *is* its shape - no
        separate stored counter, and nothing to keep in sync.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_finished_route_shapes
        """
        if self.sink is None:
            return []
        rows = self.sink.graph_store.get_progress_table_rows()
        return [row["url"] for row in rows if row.get("status") == "Finished"]

    def _resume_urls(self) -> List[str]:
        """Pages a previous run left unfinished, so a crawl that stopped early
        picks up where it stopped instead of re-deriving the whole frontier
        from `start_url`.

        Reads `GraphStore.get_pending`, which has existed on the interface and
        in both backends all along with no caller. Needs a sink: without one
        there is no store holding a previous run's progress.

        A shaped URL carrying a `{token}` placeholder is skipped - it is a
        canonical storage key, not a navigable address, so there is nothing to
        fetch. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_resume_urls
        """
        if self.sink is None:
            return []
        pending = self.sink.graph_store.get_pending()
        return [url for url in pending if "{token}" not in url]

    def _scouted_urls(self) -> List[str]:
        """Pages phase 1 finished scouting - what phase 2's frontier is
        built from. Same `{token}` filter as `_resume_urls`: a shaped URL
        carrying a placeholder is a canonical storage key, not a navigable
        address. Empty (not an error) without a sink - no store, no way
        `"Scouted"` was ever written.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_scouted_urls
        """
        if self.sink is None:
            return []
        scouted = self.sink.graph_store.get_scouted()
        return [url for url in scouted if "{token}" not in url]

    async def _run_sweep(
        self,
        visit_fn: Callable[[str, Optional[str]], Awaitable[PageVisitResult]],
        count_as_finished: bool,
    ) -> None:
        """Spin up `page_concurrency` workers draining the frontier with
        `visit_fn` until empty, then tear them down - one full site-wide
        pass. Called once (`PageVisitor.visit`) for the default fused crawl,
        or twice (`scout` then `interact`) under `two_phase_crawl`.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_run_sweep
        """
        workers = [
            asyncio.create_task(self._worker(i, visit_fn, count_as_finished))
            for i in range(self._pacing.page_concurrency)
        ]
        await self._frontier.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def crawl_site(self, start_url: str) -> List[PageVisitResult]:
        """Crawl every page reachable from `start_url`, `page_concurrency` at
        a time. Under `scout_only`, runs a single scout sweep and returns,
        leaving every page `"Scouted"` for a later, separate crawl to pick
        up. Under `two_phase_crawl`, runs that same scout sweep to
        completion first, then rebuilds the frontier from every page it
        left `"Scouted"` and runs a full interact sweep in this same
        process - see `MechanicalCrawlerConfig.two_phase_crawl` for why.
        Under `interact_only`, skips discovery in this process entirely and
        runs only the interact sweep, over whatever an earlier, separate
        `scout_only` run already left `"Scouted"` - see
        `MechanicalCrawlerConfig.interact_only`.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site
        """
        if self._frontier.base_url is None:
            self._frontier.base_url = start_url
        # Before any enqueue: the route-shape gate runs inside enqueue, so
        # priming afterwards would let already-sampled shapes back in.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site-prime
        self._frontier.prime_route_shape_visits(self._finished_route_shapes())
        if self._interact_only:
            # No discovery in this process at all: `start_url` itself is
            # never enqueued, only whatever a previous, separate run left
            # "Scouted" - see MechanicalCrawlerConfig.interact_only.
            # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site-interact_only
            for url in self._scouted_urls():
                self._frontier.enqueue_scouted(url)
            await self._run_sweep(self._page_visitor.interact, count_as_finished=True)
            return self.page_results
        self._frontier.enqueue(start_url)
        # After start_url, so the entry point is always visited first.
        # `enqueue` re-applies scope, dedup and the route-shape cap, so a
        # stale or now-out-of-scope pending URL is filtered here rather than
        # trusted. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site-resume
        resumed = self._resume_urls()
        if resumed:
            print(f"Resuming: {len(resumed)} page(s) left pending by a previous run.")
            for url in resumed:
                self._frontier.enqueue(url)
        if self._scout_only:
            await self._run_sweep(self._page_visitor.scout, count_as_finished=False)
        elif self._two_phase_crawl:
            await self._run_sweep(self._page_visitor.scout, count_as_finished=False)
            for url in self._scouted_urls():
                self._frontier.enqueue_scouted(url)
            await self._run_sweep(self._page_visitor.interact, count_as_finished=True)
        else:
            await self._run_sweep(self._page_visitor.visit, count_as_finished=True)
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

    def _budget_exhausted(self) -> bool:
        """Whether this run is done taking new pages, announcing the reason
        the first time so it is said once rather than once per worker.
        Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_budget_exhausted
        """
        if self.stopped_reason is not None:
            return True
        reason = self._budget.exhausted_reason()
        if reason is None:
            return False
        self.stopped_reason = reason
        print(
            f"\nStopping this run: {reason}. "
            f"{self._frontier.queued_count()} page(s) stay pending for the next one."
        )
        return True

    def _report_visit(self, worker_id: int, url: str, outcome: str) -> None:
        """One line per finished visit, naming the worker so concurrent
        output stays readable, and splitting unique visits from requeues so a
        crawl churning on the same pages is visibly different from one making
        progress. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_report_visit
        """
        print(
            f"worker {worker_id} | visit {self._pages_visited} "
            f"({self._unique_visits} unique, {self._requeued_visits} requeued, "
            f"{self._gave_up_visits} gave up) "
            f"| queued: {self._frontier.queued_count()} | {outcome}: {url}"
        )

    async def _worker(
        self,
        worker_id: int,
        visit_fn: Callable[[str, Optional[str]], Awaitable[PageVisitResult]],
        count_as_finished: bool,
    ) -> None:
        """One concurrent visitor: pulls a URL, hands it to `visit_fn`
        (`PageVisitor.visit`/`scout`/`interact`, chosen by `_run_sweep`),
        requeues. Reuses one browser tab (keyed by `worker_id`) across every
        URL it visits, so tab count stays at `page_concurrency` for the whole
        crawl instead of growing by one per page - periodically recycled,
        see `_recycle_session_if_due`.

        `count_as_finished` gates whether a completed pass counts as a real
        completion (`CrawlBudget.pages`, `_unique_visits`, and - critically -
        `tracker.mark_visited`) or only as scouted: a scout pass marking a
        page visited would make phase 2's own dequeue gate below skip every
        page it just scouted, so the interact sweep would silently do
        nothing. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker
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
                # Same drain-don't-break discipline as max_pages above: the
                # queue still has to be consumed and task_done()'d or
                # crawl_site's join() never returns. Whatever is drained here
                # stays Pending in the graph, which is what the next run
                # resumes from. Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-budget
                if self._budget_exhausted():
                    continue
                key = clean_url(url)
                if self.tracker.is_visited(key):
                    continue
                if self._frontier.is_in_flight(key):
                    continue  # duplicate dequeue - see docs/dev/spiders/orchestration/mechanical_loop/frontier.md#in_flight
                self._frontier.mark_in_flight(key)
                try:
                    result = await visit_fn(url, browser_session_id)
                finally:
                    self._frontier.clear_in_flight(key)
                visits_since_recycle += 1
                visits_since_recycle = await self._recycle_session_if_due(browser_session_id, visits_since_recycle)
                self.page_results.append(result)
                self._pages_visited += 1
                # The page node plus everything discovered on it - an estimate
                # of graph growth, not a query, so the budget check stays free.
                # Counted regardless of interruption: record_inventory/
                # record_page_arrival already wrote this data to the store
                # before any interruption could happen.
                # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#budget-nodes
                self._budget.record_nodes(
                    1 + result.components_discovered + result.links_discovered
                )
                if result.interrupted_by_navigation:
                    # Requeue resolved_url directly - see doc for the redirect bug this avoids.
                    # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-requeue
                    self._requeued_visits += 1
                    if self._frontier.requeue(result.resolved_url):
                        outcome = "requeued"
                    else:
                        # Past max_requeue_attempts for this url - give up
                        # for good rather than cycle forever. Marked visited
                        # in both places a normal finish would be: the
                        # tracker cache (so this process never reconsiders
                        # it) and the store (so a resumed run doesn't either).
                        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-give-up
                        outcome = "gave up on"
                        self._gave_up_visits += 1
                        self.tracker.mark_visited(key)
                        if self.sink:
                            await self.sink.record_page_failed(result.url)
                else:
                    self._frontier.record_route_shape_visit(url)
                    if count_as_finished:
                        # CrawlBudget.pages counts "pages finished this run" (its
                        # own docstring) - only here, never for a requeued/
                        # interrupted pass, which hasn't finished and will be
                        # reattempted. Counting those too let a site whose
                        # anti-bot protection intermittently blocks requests burn
                        # its whole page budget re-requeuing the same handful of
                        # pages, reporting "budget reached" while hundreds of
                        # newly discovered URLs never got a turn.
                        # Details: docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-budget
                        self._budget.record_page()
                        self._unique_visits += 1
                        # See _worker's own docstring for why this stays gated on
                        # count_as_finished rather than running unconditionally.
                        self.tracker.mark_visited(key)
                        outcome = "done"
                    else:
                        outcome = "scouted"
                self._report_visit(worker_id, url, outcome)
            finally:
                self._frontier.task_done()
