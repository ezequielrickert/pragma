"""The shared crawl-engine core issue #241 assembles: one class,
parameterized by discovery mode, that `StaticEngine`/`DynamicEngine` sit
on top of as thin config presets - per the design locked in issue #236 and
built from the two standalone collaborators issues #239/#240 already
delivered (`PragmaDeepCrawlStrategy`, `PageInteractionStep`). Replaces
`spiders/orchestration/mechanical_loop/`/`spiders/orchestration/
page_visitor/` outright: no `UrlFrontier`, no `WorkerPacing`, no
`CrawlBudget` - see this module's own docstrings below for what took each
one's place.

**Why this isn't `crawler.arun(config=CrawlerRunConfig(deep_crawl_strategy=
PragmaDeepCrawlStrategy(...)))`, despite #239's own docstring saying
concurrency would come from crawl4ai's own dispatcher.** Checked live
(`crawl4ai==0.9.2`): `BFSDeepCrawlStrategy._arun_batch` clones ONE
`CrawlerRunConfig` for the whole batch and calls `crawler.arun_many(urls,
config=batch_config)`; its dispatcher (`MemoryAdaptiveDispatcher`) passes
`session_id=task_id` to `crawler.arun()` as a bare keyword argument, which
`AsyncWebCrawler.arun()` silently drops (`**kwargs` is never read for it) -
so every concurrent fetch in a batch shares whatever `session_id` the
original config carried (`None`, falling back to `"default"`). This
project's own `HookHandlers` stashes each navigation's extraction under
`config.session_id`, so N concurrent fetches racing to write/pop the same
`"default"` stash entry silently cross-attributes one page's components to
another. Real navigation stays safe either way (crawl4ai only reuses a
Playwright page when `session_id` is truthy and already known), but the
extraction data is not. Fix applied here: `PragmaDeepCrawlStrategy` still
owns every frontier decision (`can_process_url`/`link_discovery` - scope,
dedup, the route-shape cap), called directly against the real crawl4ai
`CrawlResult` `discover_page_with_result` already returns; concurrency
comes from this module's own small bounded worker pool, reusing the
same stable-`session_id`-per-worker-slot scheme `discover_page` has always
used safely (`f"worker-{n}"`, one browser tab per slot for the run's
lifetime - proven correct in production today). A real crawl4ai fix would
let this collapse onto the dispatcher outright; worth revisiting if one
ships upstream, not attempted here.

**Memory-ceiling worker pacing is dropped, not ported.** `WorkerPacing`'s
`memory_ceiling_percent` pause and `target_slowdown_ratio` concurrency
taper existed because raising `page_concurrency` was otherwise "a faster
way to reproduce the same OOM" (its own prior docstring). #236's design
expected crawl4ai's own `MemoryAdaptiveDispatcher` to absorb that job
instead - which this module can't lean on for the reason above. Dropped
outright rather than reimplemented: the same "simplify first, rebuild
controls later only if a real need shows up" call this map's Destination
already made for per-run budgets, extended here to worker pacing too.
`TargetLoadThrottle` (backoff/circuit-breaker against a straining target
server, owned by `Crawl4AICrawler` itself) is untouched and still applies.
Details: docs/dev/spiders/orchestration/engine_core.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from core.data_contracts import PageState
from utils.urls import restore_scheme, route_shape
from ..content.fill_values import default_placeholder_fill_value
from .deep_crawl_strategy import PragmaDeepCrawlStrategy
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
    session_recycle_after: Optional[int] = 15
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
        self.session_recycle_after = config.session_recycle_after
        self.tracker: InteractionTracker = (
            GraphStoreInteractionTracker(config.sink.graph_store) if config.sink is not None
            else InMemoryInteractionTracker()
        )
        self.strategy = PragmaDeepCrawlStrategy(
            base_url=config.base_url,
            allow_subdomains=config.allow_subdomains,
            max_visits_per_route_shape=config.max_visits_per_route_shape,
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
        self._visits_since_recycle: Dict[int, int] = {}

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

    async def _recycle_session_if_due(self, worker_id: int, session_id: str) -> None:
        """Close `session_id`'s tab once it's carried `session_recycle_after`
        visits, so crawl4ai rebuilds a fresh one on this worker's next
        fetch - ported unchanged from `MechanicalCrawler._recycle_session_if_due`.
        Details: docs/dev/spiders/orchestration/engine_core.md#_recycle_session_if_due
        """
        if self.session_recycle_after is None:
            return
        visits = self._visits_since_recycle.get(worker_id, 0) + 1
        if visits < self.session_recycle_after:
            self._visits_since_recycle[worker_id] = visits
            return
        close = getattr(self.crawler, "close_session", None)
        if close is not None:
            try:
                await close(session_id)
            except Exception as exc:
                print(f"Warning: could not recycle session {session_id!r}: {exc}")
        self._visits_since_recycle[worker_id] = 0

    async def _fetch_level(
        self, urls: List[str]
    ) -> List[Tuple[str, Optional[PageState], Optional[Any], str]]:
        """Fetch every URL in one BFS level, `page_concurrency` workers at
        a time - each worker owns one stable `session_id` for the whole
        run (`f"worker-{n}"`), the same scheme `discover_page` has always
        used safely, sidestepping the session-collision this module's own
        docstring explains. Returns `(url, page_state_or_none,
        raw_result_or_none, session_id)` per URL - `session_id` is the live
        browser tab a caller must reuse to interact with this same page
        (`None`/`None` state/result for a failed fetch, session_id still
        meaningful for bookkeeping), so one page's navigation failure never
        crashes the level.
        Details: docs/dev/spiders/orchestration/engine_core.md#_fetch_level
        """
        queue: "asyncio.Queue[str]" = asyncio.Queue()
        for url in urls:
            queue.put_nowait(url)
        results: List[Tuple[str, Optional[PageState], Optional[Any], str]] = []
        lock = asyncio.Lock()

        async def worker(worker_id: int) -> None:
            session_id = f"worker-{worker_id}"
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    state, raw = await self.crawler.discover_page_with_result(url, session_id=session_id)
                    await self._recycle_session_if_due(worker_id, session_id)
                    async with lock:
                        results.append((url, state, raw, session_id))
                except Exception as exc:
                    print(f"Warning: could not discover {url!r}, skipping: {exc}")
                    async with lock:
                        results.append((url, None, None, session_id))
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(worker(i)) for i in range(min(self.page_concurrency, len(urls)))
        ]
        await asyncio.gather(*workers)
        return results

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
        result = await self.interaction_step.interact(url, session_id, state)
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
        """Level-by-level BFS over the site, deferring every admission/dedup/
        route-shape decision to `PragmaDeepCrawlStrategy` - the frontier
        loop `UrlFrontier`+the worker loop in the old `mechanical_loop/
        loop.py` used to own. `scout`/`fused` only; `interact` mode never
        calls this (nothing to discover - see `run`).
        Details: docs/dev/spiders/orchestration/engine_core.md#_run_discovery
        """
        self.strategy.prime_route_shape_visits(self._finished_route_shapes())
        visited: Set[str] = set()
        depths: Dict[str, int] = {start_url: 0}
        current_level: List[Tuple[str, Optional[str]]] = [(start_url, None)]
        # depth=1, not 0: `can_process_url`'s own depth==0 case always
        # admits the entry point unconditionally, and a resumed URL isn't
        # one - it must clear the same route-shape cap a freshly
        # discovered link would, the same re-gating `UrlFrontier.enqueue`
        # used to apply to every resumed URL (issue #242's own test
        # coverage caught this admitted-uncapped gap during the Legacy
        # Engine's retirement).
        for url in self._resume_urls():
            if url not in depths and await self.strategy.can_process_url(url, 1):
                current_level.append((url, None))
                depths[url] = 0

        while current_level:
            if self._max_pages_reached():
                break
            urls = [url for url, _ in current_level]
            next_level: List[Tuple[str, Optional[str]]] = []
            for url, state, raw_result, session_id in await self._fetch_level(urls):
                if state is None or raw_result is None:
                    continue
                self._pages_visited += 1
                depth = depths.get(url, 0)
                await self.strategy.link_discovery(raw_result, url, depth, visited, next_level, depths)
                await self._process_page(url, session_id, state, mode)
                if self._max_pages_reached():
                    next_level = []
                    break
            current_level = next_level

    async def _run_interact(self) -> None:
        """`interact` mode: no discovery, a flat single-level pass over
        whatever a previous, separate scout run already left `"Scouted"` -
        `pragma dynamic`'s own resume mode.
        Details: docs/dev/spiders/orchestration/engine_core.md#_run_interact
        """
        for url in self._scouted_urls():
            if self._max_pages_reached():
                break
            for _, state, _, session_id in await self._fetch_level([url]):
                if state is None:
                    continue
                self._pages_visited += 1
                await self._process_page(url, session_id, state, INTERACT)

    async def run(self, start_url: str, mode: DiscoveryMode = FUSED) -> List[PageVisitResult]:
        """Crawl `start_url`'s site under `mode`. Details: docs/dev/spiders/orchestration/engine_core.md#run"""
        if self.strategy.base_url is None:
            self.strategy.base_url = start_url
        if mode == INTERACT:
            await self._run_interact()
        else:
            await self._run_discovery(start_url, mode)
        return self.page_results
