"""The shared crawl-engine core issue #241 assembles: one class,
parameterized by discovery mode, that `StaticEngine`/`DynamicEngine` sit
on top of as thin config presets - per the design locked in issue #236 and
built from the two standalone collaborators issues #239/#240 already
delivered (`PragmaDeepCrawlStrategy`, `PageInteractionStep`). Replaces
`spiders/orchestration/mechanical_loop/`/`spiders/orchestration/
page_visitor/` outright: no `UrlFrontier`, no `WorkerPacing`, no
`CrawlBudget` - see this module's own docstrings below for what took each
one's place.

**Now runs on `crawler.arun(config=CrawlerRunConfig(deep_crawl_strategy=
PragmaBestFirstStrategy(...), stream=True))` directly - issue #249,
reversing this module's own original call.** Checked live
(`crawl4ai==0.9.2`) while this module was first built: `BFSDeepCrawlStrategy
._arun_batch`'s dispatcher (`MemoryAdaptiveDispatcher`) passed
`session_id=task_id` to `crawler.arun()` as a bare keyword argument that
`AsyncWebCrawler.arun()` silently dropped, so every concurrent fetch in a
batch shared one `session_id` and cross-attributed extraction data between
pages. That's what this module's own hand-rolled worker pool
(`_fetch_level`, one stable `f"worker-{n}"` session per slot) existed to
route around. The underlying bug is fixed now, at its own resolution
point (`SessionAwareDispatcher`, issue #246) rather than worked around
here, and `PragmaBestFirstStrategy` (issue #247) carries the same
frontier rules `PragmaDeepCrawlStrategy` always did
(`can_process_url`/`link_discovery`) plus that fixed dispatcher - so the
worker pool this module used to own is gone: `Crawl4AICrawler.deep_crawl`
(scout/fused discovery) and `.discover_many` (interact mode's flat pass)
both stream straight off crawl4ai's own `arun`/`arun_many`+dispatcher,
concurrency bounded by `page_concurrency` there instead of here. One
consequence: every page now gets its own single-use dispatcher-assigned
session instead of a long-lived per-worker one, so `_close_session_quietly`
closes each one right after that page's own discovery+interaction pass
finishes, replacing the old periodic `session_recycle_after` model
outright (a *shared* tab's own growth was what that guarded against; a
single-use tab has nothing to grow into). Another: `Crawl4AICrawler
.deep_crawl`/`.discover_many` don't wrap each navigation in
`_run_with_watchdog`/`TargetLoadThrottle` the way the retired worker pool's
own `discover_page_with_result` calls did - see that method's own module
docstring for the trade-off.

**Memory-ceiling worker pacing is dropped, not ported.** `WorkerPacing`'s
`memory_ceiling_percent` pause and `target_slowdown_ratio` concurrency
taper existed because raising `page_concurrency` was otherwise "a faster
way to reproduce the same OOM" (its own prior docstring). #236's design
expected crawl4ai's own `MemoryAdaptiveDispatcher` to absorb that job
instead, which issue #249 finally hands it. Not reinstated as a separate
mechanism on top: the same "simplify first, rebuild controls later only
if a real need shows up" call this map's Destination already made for
per-run budgets, extended here to worker pacing too.
Details: docs/dev/spiders/orchestration/engine_core.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.data_contracts import PageState
from utils.urls import restore_scheme, route_shape
from ..browser.crawl4ai_crawler.session_aware_dispatcher import SessionAwareDispatcher
from ..content.fill_values import default_placeholder_fill_value
from .best_first_strategy import PragmaBestFirstStrategy
from .graph_sink import GraphStoreInteractionTracker, GraphStoreSink
from .interaction_tracker import InMemoryInteractionTracker, InteractionTracker
from .page_interaction import PageInteractionStep
from .visit_result import PageVisitResult

FillValueFn = Callable[[Dict[str, Any], str], Awaitable[str]]

# The three discovery modes CrawlEngineCore.run() supports - "scout"
# (pragma static: discover and record, never interact), "interact"
# (pragma dynamic's resume mode: no discovery, interact with pages a prior
# scout run already left "Scouted"), "fused" (today's Engine default:
# discover and interact in the same pass, used when there is nothing to
# resume from). Details: docs/dev/spiders/orchestration/engine_core.md#discoverymode
DiscoveryMode = str
SCOUT: DiscoveryMode = "scout"
INTERACT: DiscoveryMode = "interact"
FUSED: DiscoveryMode = "fused"


@dataclass
class EngineCoreConfig:
    """Every tuning knob `CrawlEngineCore` accepts beyond the crawler
    itself - the single config surface `StaticEngine`/`DynamicEngine`
    build from instead of each wiring their own crawler+loop from scratch.
    Details: docs/dev/spiders/orchestration/engine_core.md#enginecoreconfig
    """

    sink: Optional[GraphStoreSink] = None
    fill_value_fn: FillValueFn = default_placeholder_fill_value
    max_pages: Optional[int] = None
    page_concurrency: int = 4
    base_url: Optional[str] = None
    allow_subdomains: bool = False
    max_visits_per_route_shape: int = 1
    family_sampler: Optional[Any] = None
    exact_reuse_index: Optional[Any] = None


class CrawlEngineCore:
    """One shared crawl loop, parameterized by discovery mode - the class
    `StaticEngine.run()`/`DynamicEngine.run()` both drive instead of each
    wiring `Crawl4AICrawler`+`MechanicalCrawler` independently.
    Details: docs/dev/spiders/orchestration/engine_core.md#crawlenginecore
    """

    def __init__(self, crawler: Any, config: Optional[EngineCoreConfig] = None) -> None:
        config = config or EngineCoreConfig()
        self.crawler = crawler
        self.sink = config.sink
        self.max_pages = config.max_pages
        self.page_concurrency = max(1, config.page_concurrency)
        self.tracker: InteractionTracker = (
            GraphStoreInteractionTracker(config.sink.graph_store) if config.sink is not None
            else InMemoryInteractionTracker()
        )
        self.strategy = PragmaBestFirstStrategy(
            base_url=config.base_url,
            allow_subdomains=config.allow_subdomains,
            max_visits_per_route_shape=config.max_visits_per_route_shape,
            max_pages=float("inf") if config.max_pages is None else config.max_pages,
            max_session_permit=self.page_concurrency,
        )
        self.interaction_step = PageInteractionStep(
            crawler, self.tracker, config.fill_value_fn,
            exact_reuse_index=config.exact_reuse_index,
            family_sampler=config.family_sampler,
            sink=config.sink,
            is_known_url=self.strategy.is_known,
        )
        self.page_results: List[PageVisitResult] = []
        self._pages_visited = 0

    def _finished_route_shapes(self) -> List[str]:
        """Route shapes a previous run already sampled - same source and
        purpose as `MechanicalCrawler._finished_route_shapes`.
        Details: docs/dev/spiders/orchestration/engine_core.md#_finished_route_shapes
        """
        if self.sink is None:
            return []
        rows = self.sink.graph_store.get_progress_table_rows()
        return [row["url"] for row in rows if row.get("status") == "Finished"]

    def _resume_urls(self) -> List[str]:
        """Pages a previous run left unfinished - crash-resilience carried
        over unchanged from `MechanicalCrawler._resume_urls` (see its own
        docstring); the one piece of the old resume machinery issue #236
        kept.
        Details: docs/dev/spiders/orchestration/engine_core.md#_resume_urls
        """
        if self.sink is None:
            return []
        pending = self.sink.graph_store.get_pending()
        return [
            restore_scheme(url, self.strategy.base_url)
            for url in pending if "{token}" not in url
        ]

    def _scouted_urls(self) -> List[str]:
        """Pages a previous scout run finished scouting - what `interact`
        mode's flat, single-level pass runs over.
        Details: docs/dev/spiders/orchestration/engine_core.md#_scouted_urls
        """
        if self.sink is None:
            return []
        scouted = self.sink.graph_store.get_scouted()
        return [
            restore_scheme(url, self.strategy.base_url)
            for url in scouted if "{token}" not in url
        ]

    async def _close_session_quietly(self, session_id: str) -> None:
        """Release this page's single-use browser tab once its discovery+
        interaction pass is fully done. Every page fetched off the native
        dispatcher (`Crawl4AICrawler.deep_crawl`/`.discover_many`, issue
        #249) gets its own dispatcher-assigned session that nothing else
        will ever reuse - unlike the retired worker pool's shared
        `f"worker-{n}"` sessions, closing it once here, right after, is
        what stands in for `_recycle_session_if_due`'s old periodic-close
        model: that one bounded how long a *shared* tab could go without a
        fresh one, a problem a single-use tab no longer has. Swallows
        `close_session`'s own failures - ported from that method's
        identical broad `except`: a wedged/timed-out close must never take
        the crawl down.
        Details: docs/dev/spiders/orchestration/engine_core.md#_close_session_quietly
        """
        close = getattr(self.crawler, "close_session", None)
        if close is None:
            return
        try:
            await close(session_id)
        except Exception as exc:
            print(f"Warning: could not close session {session_id!r}: {exc}")

    def _seed_resume_state(self, start_url: str, resume_urls: List[str]) -> Dict[str, Any]:
        """`PragmaBestFirstStrategy`'s native `resume_state` contract wants
        a `queue_items` list carrying a `score`/`depth`/`parent_url` per
        outstanding URL (issue #248's research) - `GraphStore.get_pending()`
        has none of that, only bare URLs. What this seeds is the same
        coarser thing `_run_discovery`'s old BFS loop always did with
        `_resume_urls()`: readmit every pending URL as a fresh depth-1
        queue entry (the caller re-gates each one through `can_process_url`
        first - `depth=1, not 0`, so a resumed URL clears the same
        route-shape cap a freshly discovered link would, per the old loop's
        own comment on why). A resumed run loses its previous queue
        *ordering*, not its set of outstanding work; recovering the real
        ordering would need pragma's graph to persist score/depth/parent_url
        per page, which issue #248 found it doesn't (new read/write surface
        on `LadybugGraphStore`, not this ticket's scope).

        `score` is negated: `_arun_best_first` treats a fresh `resume_state`
        queue as already carrying the negated, min-heap-ready score its own
        `_on_state_change` callback exports (confirmed against that
        callback's shape, issue #248) - un-negated here would invert this
        run's whole priority order against `start_url`'s own entry, which
        this method scores the exact same way `_arun_best_first` scores it
        when there's no resume state at all.
        Details: docs/dev/spiders/orchestration/engine_core.md#_seed_resume_state
        """
        def negated_score(url: str) -> float:
            return -self.strategy.url_scorer.score(url) if self.strategy.url_scorer else 0

        queue_items = [{"score": negated_score(start_url), "depth": 0, "url": start_url, "parent_url": None}]
        queue_items += [
            {"score": negated_score(url), "depth": 1, "url": url, "parent_url": None} for url in resume_urls
        ]
        return {
            "visited": [],
            "depths": {start_url: 0, **{url: 1 for url in resume_urls}},
            "pages_crawled": 0,
            "queue_items": queue_items,
        }

    async def _record_discovery(self, page_key: str, state: PageState) -> None:
        """The seven sink writes owed for every freshly discovered page -
        ported unchanged from `PageVisitor._record_discovery`.
        Details: docs/dev/spiders/orchestration/engine_core.md#_record_discovery
        """
        if not self.sink:
            return
        await self.sink.record_page_arrival(page_key, description=state.description, title=state.title)
        await self.sink.record_inventory(
            page_key, self.interaction_step.canonicalize_inventory(page_key, state.components), state.links
        )
        await self.sink.record_text_content(page_key, state.text_content)
        await self.sink.record_state_styles(page_key, state.pseudo_styles)
        await self.sink.record_accessibility_snapshot(page_key, state.aria_snapshot_yaml, state.axtree_json)
        await self.sink.record_page_network(page_key, state.network_requests)
        await self.sink.record_page_metadata(page_key, state.metadata)

    async def _process_page(self, url: str, session_id: str, state: PageState, mode: DiscoveryMode) -> None:
        """Record a freshly discovered page and, outside `scout` mode,
        interact with it immediately over the same live session it was
        just fetched under - `scout` mode records and stops.
        Details: docs/dev/spiders/orchestration/engine_core.md#_process_page
        """
        page_key = route_shape(state.url)
        if mode != INTERACT:
            # `interact` mode's own page was already recorded by an
            # earlier, separate scout pass - see PageVisitor.interact's
            # prior docstring for the same skip.
            await self._record_discovery(page_key, state)
        if mode == SCOUT:
            if self.sink:
                await self.sink.record_page_scouted(page_key, len(state.components))
            self.page_results.append(PageVisitResult(
                url=page_key, resolved_url=state.url,
                components_discovered=len(state.components), links_discovered=len(state.links),
            ))
            return
        await self._interact_with_resumes(url, session_id, state)

    async def _interact_with_resumes(self, url: str, session_id: str, state: PageState) -> None:
        """`PageInteractionStep.interact()`, re-fetching and re-running the
        origin page whenever a navigating click interrupted the pass before
        its frontier drained - issue #243: `PageInteractionStep` (#236)
        deliberately dropped the old `MechanicalCrawler`'s follow-up-pass
        requeue as part of simplifying the interaction step down to "one
        pass over one already-fetched state," but that requeue was load-
        bearing for coverage, not just recovery plumbing - without it, any
        component sitting later in DOM order than the first navigating
        link on a page (a modal trigger, a share/favorite button on a
        listing card whose own title link navigates) never got a chance to
        be interacted with at all. `PageInteractionStep` itself is
        untouched - it still correctly ends one pass at the first
        navigation; this decides what happens next.

        Each resume re-fetches the *origin* page fresh (the live session is
        on the navigated-to page by now) and hands it to another
        `interact()` call. This terminates on its own, no iteration cap
        needed: `InteractionTracker` marks a component interacted before
        `interact()` can ever break on it, so every resume's eligible set
        (`visible and not yet interacted`) is strictly smaller than the
        one before - bounded by the page's own finite component count, the
        same way the old loop's requeue converged.
        Details: docs/dev/spiders/orchestration/engine_core.md#_interact_with_resumes
        """
        result = await self.interaction_step.interact(url, session_id, state)
        self.page_results.append(result)
        while result.interrupted_by_navigation:
            origin_url = result.resolved_url
            resumed_state, _ = await self.crawler.discover_page_with_result(origin_url, session_id=session_id)
            if resumed_state is None:
                break
            result = await self.interaction_step.interact(origin_url, session_id, resumed_state)
            self.page_results.append(result)

    def _max_pages_reached(self) -> bool:
        """Whether this run has visited its `max_pages` cap - shared by
        `_run_discovery` and `_run_interact`'s otherwise-identical stop
        check, each called once per level/page rather than per worker, so
        the reason prints at most a handful of times, not once per visit.
        Details: docs/dev/spiders/orchestration/engine_core.md#_max_pages_reached
        """
        if self.max_pages is None or self._pages_visited < self.max_pages:
            return False
        print(f"Stopping this run: page budget reached ({self._pages_visited}/{self.max_pages} pages).")
        return True

    async def _run_discovery(self, start_url: str, mode: DiscoveryMode) -> None:
        """Streams the whole crawl off `PragmaBestFirstStrategy`'s own
        best-first traversal (`Crawl4AICrawler.deep_crawl`) instead of the
        retired level-by-level worker pool - issue #249. `scout`/`fused`
        only; `interact` mode never calls this (nothing to discover - see
        `run`).
        Details: docs/dev/spiders/orchestration/engine_core.md#_run_discovery
        """
        self.strategy.prime_route_shape_visits(self._finished_route_shapes())
        resume_urls: List[str] = []
        for url in self._resume_urls():
            # Re-gated through can_process_url the same way the retired BFS
            # loop's own "depth=1, not 0" comment explained: a resumed URL
            # isn't the entry point, so it must clear the same route-shape
            # cap a freshly discovered link would.
            if url not in resume_urls and await self.strategy.can_process_url(url, 1):
                resume_urls.append(url)
        if resume_urls:
            self.strategy._resume_state = self._seed_resume_state(start_url, resume_urls)

        async for state, result, session_id in self.crawler.deep_crawl(start_url, self.strategy):
            try:
                if state is None:
                    continue
                self._pages_visited += 1
                await self._process_page(result.url, session_id, state, mode)
                if self._max_pages_reached():
                    break
            finally:
                await self._close_session_quietly(session_id)

    async def _run_interact(self) -> None:
        """`interact` mode: no discovery, a flat pass over whatever a
        previous, separate scout run already left `"Scouted"` - `pragma
        dynamic`'s own resume mode. Genuinely concurrent now (issue #249):
        `Crawl4AICrawler.discover_many`/`SessionAwareDispatcher` replace
        the retired `_fetch_level`, which - despite `page_concurrency`
        being one of this class's own config knobs - only ever ran one
        worker here (`_fetch_level([url])`, a single URL per call inside a
        sequential outer loop over `_scouted_urls()`); that knob was dead
        weight in this mode before this ticket.
        Details: docs/dev/spiders/orchestration/engine_core.md#_run_interact
        """
        urls = self._scouted_urls()
        if not urls:
            return
        if self.max_pages is not None:
            urls = urls[: self.max_pages]
        dispatcher = SessionAwareDispatcher(max_session_permit=self.page_concurrency)
        async for url, state, _, session_id in self.crawler.discover_many(urls, dispatcher):
            try:
                if state is None:
                    continue
                self._pages_visited += 1
                await self._process_page(url, session_id, state, INTERACT)
            finally:
                await self._close_session_quietly(session_id)

    async def run(self, start_url: str, mode: DiscoveryMode = FUSED) -> List[PageVisitResult]:
        """Crawl `start_url`'s site under `mode`. Details: docs/dev/spiders/orchestration/engine_core.md#run"""
        if self.strategy.base_url is None:
            self.strategy.base_url = start_url
        if mode == INTERACT:
            await self._run_interact()
        else:
            await self._run_discovery(start_url, mode)
        return self.page_results
