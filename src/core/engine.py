"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.
Details: docs/dev/core/engine.md#module
"""
from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlparse

from ..crawlers.crawl4ai_crawler import Crawl4AICrawlerConfig
from ..crawlers.crawl4ai_crawler_pool import Crawl4AICrawlerPool
from ..crawlers.crawl_stopper import CrawlStopper, SessionBudget, StopReason
from ..crawlers.debug_log import CrawlDebugLog, prune_old_runs
from ..crawlers.fill_value_agent import make_ai_fill_value_fn
from ..crawlers.fill_values import default_placeholder_fill_value
from ..crawlers.graph_sink import GraphStoreSink
from ..crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from ..crawlers.resume_state import restore_frontier
from ..generators.component_tree import generate_component_tree_document
from ..generators.graph_export import generate_graph_export_document
from ..generators.graph_prd_synthesizer import GraphPRDSynthesizer
from ..generators.whole_site_passes import apply_component_families, apply_request_graph
from ..utils.io import generate_docs_index, record_run_manifest, write_output
from .config import PragmaConfig
from .interfaces import Agent, GraphStore
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def _slugify(url: str) -> str:
    """Turn URL into a filesystem-safe slug."""
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def _timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_pool_size(browser_pool_size: Optional[int], page_concurrency: int) -> int:
    """How many real Chromium processes Crawl4AICrawlerPool should launch.
    Unset ties it to page_concurrency (one dedicated browser per worker);
    set, it's clamped so no pool member ever sits idle with no worker
    routed to it. Details: docs/dev/core/engine.md#_resolve_pool_size
    """
    if browser_pool_size is None:
        return page_concurrency
    return min(browser_pool_size, page_concurrency)


def _catch_first_interrupt(stopper: CrawlStopper) -> Callable[[], None]:
    """Turn one Ctrl-C into a clean end-of-session instead of a traceback,
    and return the callback that undoes it.

    Args:
        stopper: asked to stop when SIGINT arrives.

    Returns:
        A no-argument callable restoring the default SIGINT behaviour;
        call it once the crawl is over. The handler removes itself as it
        fires, so a *second* Ctrl-C still aborts immediately - a user who
        doesn't want to wait out the in-flight pages must not be trapped.
        On a platform whose event loop has no signal support (Windows),
        this installs nothing and the returned callable is a no-op.
    Details: docs/dev/core/engine.md#_catch_first_interrupt
    """
    loop = asyncio.get_running_loop()

    def restore() -> None:
        try:
            loop.remove_signal_handler(signal.SIGINT)
        except (NotImplementedError, RuntimeError):
            pass

    def on_interrupt() -> None:
        restore()
        stopper.request_stop(StopReason.INTERRUPT)

    try:
        loop.add_signal_handler(signal.SIGINT, on_interrupt)
    except NotImplementedError:
        return lambda: None
    return restore


@dataclass
class _SynthesizedDocuments:
    """What one run's synthesis wrote, or nothing at all when it was skipped.
    Details: docs/dev/core/engine.md#_synthesizeddocuments
    """

    prd_path: Optional[str] = None
    tree_path: Optional[str] = None
    export_path: Optional[str] = None


@dataclass
class EngineRunResult:
    """`Engine.run()`'s return value - the output documents from one crawl.
    The document paths are `None` when a session stopped early and its
    synthesis was skipped. Details: docs/dev/core/engine.md#enginerunresult
    """

    prd_path: Optional[str] = None
    tree_path: Optional[str] = None
    export_path: Optional[str] = None
    manifest_path: str = ""
    # Browsable Markdown index of every run, regenerated fresh every run.
    # Details: docs/dev/core/engine.md#enginerunresult-index_path
    index_path: str = ""
    # Why this session ended before its frontier drained; `None` = it drained.
    # Details: docs/dev/core/engine.md#enginerunresult-stopped_reason
    stopped_reason: Optional[str] = None


class Engine:
    """Wires an agent and a graph store, then crawls a URL and synthesizes its PRD."""

    def __init__(
        self,
        agent: Agent,
        graph_store: GraphStore,
        out_dir: str = "docs",
        site: str = "",
        element_budget: int = 200,
        max_pages: Optional[int] = None,
        headless: bool = True,
        wait_seconds: float = 1.0,
        interaction_wait_seconds: Optional[float] = None,
        debug_logs_dir: str = "debug_logs",
        tree_ascii: bool = False,
        max_passes_per_page: int = 10,
        max_visits_per_route_shape: int = 1,
        ai_fill_values: bool = True,
        page_concurrency: int = 4,
        browser_pool_size: Optional[int] = None,
        page_timeout_seconds: float = 15.0,
        prefetch: bool = False,
        block_images: bool = True,
        suppress_navigation: bool = True,
        allow_subdomains: bool = False,
        debug_logs_keep_last: Optional[int] = None,
        export_json: bool = False,
        prd_synth_batch_size: int = 5,
        interaction_timeout_seconds: Optional[float] = 10.0,
        resume: bool = False,
        session_budget: Optional[SessionBudget] = None,
        synthesize_on_partial: bool = False,
    ) -> None:
        self.agent = agent
        self.graph_store = graph_store
        self.out_dir = out_dir
        self.site = site
        self.element_budget = element_budget
        self.max_pages = max_pages
        self.headless = headless
        self.wait_seconds = wait_seconds
        self.interaction_wait_seconds = interaction_wait_seconds
        self.debug_logs_dir = debug_logs_dir
        # See PragmaConfig / Crawl4AICrawlerConfig for what each changes.
        # Details: docs/dev/core/engine.md#__init__-crawl-timeouts
        self.page_timeout_seconds = page_timeout_seconds
        self.prefetch = prefetch
        self.block_images = block_images
        self.suppress_navigation = suppress_navigation
        self.interaction_timeout_seconds = interaction_timeout_seconds
        # Scope boundary for MechanicalCrawler's URL frontier.
        # Details: docs/dev/core/engine.md#__init__-allow_subdomains
        self.allow_subdomains = allow_subdomains
        self.tree_ascii = tree_ascii
        self.max_passes_per_page = max_passes_per_page
        self.max_visits_per_route_shape = max_visits_per_route_shape
        # False skips the per-fillable-field AI call entirely.
        # Details: docs/dev/core/engine.md#__init__-ai_fill_values
        self.ai_fill_values = ai_fill_values
        self.page_concurrency = page_concurrency  # see MechanicalCrawler's own docstring
        # None = tied to page_concurrency; see Crawl4AICrawlerPool's own docstring.
        # Details: docs/dev/core/engine.md#__init__-browser_pool_size
        self.browser_pool_size = browser_pool_size
        self.debug_logs_keep_last = debug_logs_keep_last
        self.export_json = export_json
        self.prd_synth_batch_size = prd_synth_batch_size
        # Seed the frontier from what a previous session left Pending in the
        # graph store, rather than from `url` alone.
        # Details: docs/dev/core/engine.md#__init__-resume
        self.resume = resume
        self.session_budget = session_budget or SessionBudget()
        self.synthesize_on_partial = synthesize_on_partial

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "Engine":
        """Resolve and wire plugins named in config via the registries."""
        provider_options = config.agents.get(config.agent, {})
        try:
            agent = AGENT_REGISTRY.create(config.agent, **provider_options)
        except Exception as exc:
            print(f"Failed to initialize {config.agent} agent: {exc}; falling back to mock")
            agent = AGENT_REGISTRY.create("mock")

        store_options = config.graph_stores.get(config.graph_store, {})
        try:
            graph_store = GRAPH_STORE_REGISTRY.create(config.graph_store, **store_options)
            graph_store.connect()
        except Exception as exc:
            print(f"Failed to initialize {config.graph_store} graph store: {exc}; falling back to memory")
            graph_store = GRAPH_STORE_REGISTRY.create("memory")
            graph_store.connect()

        site = urlparse(config.url).netloc if config.url else ""
        if config.fresh and site:
            graph_store.clear_site(site)  # no-op for InMemoryGraphStore - see PragmaConfig.fresh

        return cls(
            agent,
            graph_store,
            out_dir=config.out_dir,
            site=site,
            element_budget=config.element_budget,
            max_pages=config.max_pages,
            headless=config.headless,
            wait_seconds=config.wait_seconds,
            interaction_wait_seconds=config.interaction_wait_seconds,
            debug_logs_dir=config.debug_logs_dir,
            tree_ascii=config.tree_ascii,
            max_passes_per_page=config.max_passes_per_page,
            max_visits_per_route_shape=config.max_visits_per_route_shape,
            ai_fill_values=config.ai_fill_values,
            page_concurrency=config.page_concurrency,
            browser_pool_size=config.browser_pool_size,
            page_timeout_seconds=config.page_timeout_seconds,
            prefetch=config.prefetch,
            block_images=config.block_images,
            suppress_navigation=config.suppress_navigation,
            allow_subdomains=config.allow_subdomains,
            debug_logs_keep_last=config.debug_logs_keep_last,
            export_json=config.export_json,
            prd_synth_batch_size=config.prd_synth_batch_size,
            interaction_timeout_seconds=config.interaction_timeout_seconds,
            # Not a separate flag: `fresh` already means "discard the
            # previous run", so its inverse is exactly "continue it".
            resume=not config.fresh,
            session_budget=SessionBudget(
                stop_after_pages=config.stop_after_pages,
                stop_after_seconds=config.stop_after_seconds,
                stop_after_rate_limit_trips=config.stop_after_rate_limit_trips,
            ),
            synthesize_on_partial=config.synthesize_on_partial,
        )

    def run(self, url: str) -> EngineRunResult:
        """Crawl `url`, synthesize its PRD and component tree, write both.
        Details: docs/dev/core/engine.md#run
        """
        return asyncio.run(self._run_async(url))

    async def _run_async(self, url: str) -> EngineRunResult:
        site = self.site or urlparse(url).netloc
        sink = GraphStoreSink(self.graph_store, site)

        debug_log: Optional[CrawlDebugLog] = None
        if self.debug_logs_dir:
            run_dir = f"{self.debug_logs_dir}/{_slugify(url)}_{_timestamp()}"
            debug_log = CrawlDebugLog(run_dir, site=site)

        crawler_config = Crawl4AICrawlerConfig(
            headless=self.headless,
            wait_seconds=self.wait_seconds,
            interaction_wait_seconds=self.interaction_wait_seconds,
            debug_log=debug_log,
            page_timeout_seconds=self.page_timeout_seconds,
            prefetch=self.prefetch,
            block_images=self.block_images,
            suppress_navigation=self.suppress_navigation,
            interaction_timeout_seconds=self.interaction_timeout_seconds,
        )
        stopper = CrawlStopper(self.session_budget)
        pool_size = _resolve_pool_size(self.browser_pool_size, self.page_concurrency)
        async with Crawl4AICrawlerPool(crawler_config, pool_size=pool_size) as crawler:
            fill_value_fn = (
                make_ai_fill_value_fn(self.agent) if self.ai_fill_values else default_placeholder_fill_value
            )
            mechanical = MechanicalCrawler(
                crawler,
                config=MechanicalCrawlerConfig(
                    sink=sink,
                    element_budget=self.element_budget,
                    fill_value_fn=fill_value_fn,
                    max_pages=self.max_pages,
                    max_passes_per_page=self.max_passes_per_page,
                    max_visits_per_route_shape=self.max_visits_per_route_shape,
                    page_concurrency=self.page_concurrency,
                    base_url=url,
                    allow_subdomains=self.allow_subdomains,
                    stopper=stopper,
                ),
            )
            if self.resume:
                self._seed_previous_frontier(mechanical, site, url)
            release_interrupt = _catch_first_interrupt(stopper)
            try:
                await mechanical.crawl_site(url)
            finally:
                release_interrupt()

        stopped_reason = mechanical.stopped_reason

        if debug_log:
            await debug_log.close()
            # Prune only after close() - see prune_old_runs's own doc.
            prune_old_runs(self.debug_logs_dir, _slugify(url), self.debug_logs_keep_last)

        run_timestamp = _timestamp()
        documents = _SynthesizedDocuments()
        if self._should_synthesize(stopped_reason):
            documents = self._synthesize_documents(url, site, run_timestamp)

        finished_pages, total_pages = self.graph_store.count_visited(site)
        unexplored_components, total_components = self.graph_store.count_unexplored_components(site)
        manifest_path = record_run_manifest(
            self.out_dir,
            site,
            {
                "timestamp": run_timestamp,
                "url": url,
                "graph_store": self.graph_store.__class__.__name__,
                "prd_path": documents.prd_path,
                "tree_path": documents.tree_path,
                "export_path": documents.export_path,
                "pages_finished": finished_pages,
                "pages_total": total_pages,
                "components_total": total_components,
                "components_unexplored": unexplored_components,
                "stopped_reason": stopped_reason.value if stopped_reason else None,
            },
        )

        # Regenerated unconditionally, same as the manifest itself - cheap.
        index_doc = generate_docs_index(self.out_dir)
        index_path = f"{self.out_dir}/index.md"
        write_output(index_path, index_doc)

        self.graph_store.close()
        return EngineRunResult(
            prd_path=documents.prd_path,
            tree_path=documents.tree_path,
            export_path=documents.export_path,
            manifest_path=manifest_path,
            index_path=index_path,
            stopped_reason=stopped_reason.value if stopped_reason else None,
        )

    def _seed_previous_frontier(self, mechanical: MechanicalCrawler, site: str, start_url: str) -> None:
        """Hand `mechanical` whatever the last session left unfinished.
        Args:
            mechanical: the crawler to seed, before `crawl_site` starts it.
            site: graph-store key for this site's recorded pages.
            start_url: read only for its scheme, which the graph's
                `clean_url` keys have stripped and cannot be crawled without.
        Returns:
            None. A site with no recorded history yields an empty plan and
            the crawl proceeds normally from `start_url` alone.
        Details: docs/dev/core/engine.md#_seed_previous_frontier
        """
        plan = restore_frontier(
            self.graph_store.get_progress_table_rows(site), urlparse(start_url).scheme or "https"
        )
        if plan.is_empty:
            print(f"Nothing recorded for {site} yet - starting a fresh crawl.")
            return
        mechanical.resume(plan)

    def _should_synthesize(self, stopped_reason: Optional[StopReason]) -> bool:
        """Whether to spend LLM calls narrating a crawl that may be partial.
        Every synthesis pass re-reads the whole graph and narrates it, so on
        a session that stopped early it would be paid again in full on the
        next resume - and describe a site the crawl hasn't finished seeing.
        Details: docs/dev/core/engine.md#_should_synthesize
        """
        if stopped_reason is None:
            return True
        if self.synthesize_on_partial:
            return True
        print(
            f"Session stopped early ({stopped_reason.value}) - skipping PRD synthesis. "
            "Resume with --no-fresh, or pass --synthesize to narrate what's crawled so far."
        )
        return False

    def _synthesize_documents(self, url: str, site: str, run_timestamp: str) -> "_SynthesizedDocuments":
        """Run every whole-site pass and write the documents they produce.
        Args:
            url: the crawl's start URL, used only to name output files.
            site: which site's graph to read back.
            run_timestamp: shared suffix tying this run's files together.
        Returns:
            The paths written. The two graph-enriching passes run first and
            in order: synthesis below reads the families and inferred
            requests they write.
        Details: docs/dev/core/engine.md#_synthesize_documents
        """
        apply_component_families(self.graph_store, site, self.agent)
        apply_request_graph(self.graph_store, site)

        synthesizer = GraphPRDSynthesizer(self.agent, self.graph_store, batch_size=self.prd_synth_batch_size)
        prd_path = f"{self.out_dir}/{_slugify(url)}_prd_{run_timestamp}.md"
        write_output(prd_path, synthesizer.synthesize(site))

        tree_doc = generate_component_tree_document(self.graph_store, site, use_box_drawing=not self.tree_ascii)
        tree_path = f"{self.out_dir}/{_slugify(url)}_tree_{run_timestamp}.md"
        write_output(tree_path, tree_doc)

        export_path: Optional[str] = None
        if self.export_json:
            export_path = f"{self.out_dir}/{_slugify(url)}_graph_{run_timestamp}.json"
            write_output(export_path, generate_graph_export_document(self.graph_store, site))

        return _SynthesizedDocuments(prd_path=prd_path, tree_path=tree_path, export_path=export_path)
