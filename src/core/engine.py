"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.

Post-crawl4ai-migration: `run()` is two steps, not one - `MechanicalCrawler.crawl_site()`
writes only to `GraphStore` (via `GraphStoreSink`), then `GraphPRDSynthesizer.synthesize()`
reads only from `GraphStore` to produce the final markdown. `Crawl4AICrawler`/
`MechanicalCrawler`/`GraphPRDSynthesizer` are wired directly here rather than through a
registry - unlike agents/graph stores, there's exactly one crawling implementation now.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from ..crawlers.crawl4ai_crawler import Crawl4AICrawler
from ..crawlers.debug_log import CrawlDebugLog, prune_old_runs
from ..crawlers.fill_value_agent import make_ai_fill_value_fn
from ..crawlers.fill_values import default_placeholder_fill_value
from ..crawlers.graph_sink import GraphStoreSink
from ..crawlers.mechanical_loop import MechanicalCrawler
from ..generators.component_tree import generate_component_tree_document
from ..generators.graph_export import generate_graph_export_document
from ..generators.graph_prd_synthesizer import GraphPRDSynthesizer
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


@dataclass
class EngineRunResult:
    """`Engine.run()`'s return value - the output documents from one crawl,
    per the component-tree feature's explicit "separate output file, not
    merged into the existing prose PRD" requirement, extended the same way
    for the (opt-in) JSON export.

    `export_path` is `None` whenever `export_json` is off (the default) -
    callers should treat `None` as "not generated this run", not as a
    failure. `manifest_path` is always set: recording this run in
    `docs/runs.json` (`src/utils/io.py::record_run_manifest`) is unconditional,
    unlike the export - it's cheap bookkeeping, not an extra artifact someone
    has to opt into.
    """

    prd_path: str
    tree_path: str
    export_path: Optional[str] = None
    manifest_path: str = ""
    # docs/index.md - a browsable Markdown index of every run recorded in
    # the manifest, regenerated fresh on every run (Fase E,
    # src/utils/io.py::generate_docs_index). Always set, same as
    # manifest_path - this is bookkeeping over runs.json, not an opt-in
    # artifact.
    index_path: str = ""


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
        wait_seconds: float = 2.0,
        interaction_wait_seconds: Optional[float] = None,
        debug_logs_dir: str = "debug_logs",
        tree_ascii: bool = False,
        max_passes_per_page: int = 10,
        max_visits_per_route_shape: int = 1,
        ai_fill_values: bool = True,
        page_concurrency: int = 1,
        page_timeout_seconds: float = 15.0,
        prefetch: bool = False,
        block_images: bool = False,
        allow_subdomains: bool = False,
        debug_logs_keep_last: Optional[int] = None,
        export_json: bool = False,
        prd_synth_batch_size: int = 5,
        interaction_timeout_seconds: Optional[float] = None,
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
        # See PragmaConfig's matching fields / Crawl4AICrawler's constructor
        # docstrings for what each of these actually changes and their
        # tradeoffs (page_timeout_seconds bounds a different phase than
        # wait_seconds; prefetch empties debug markdown snapshots;
        # block_images is a real behavior change some sites may depend on).
        self.page_timeout_seconds = page_timeout_seconds
        self.prefetch = prefetch
        self.block_images = block_images
        # A third timeout phase, distinct from page_timeout_seconds - see
        # Crawl4AICrawler's own interaction_timeout_seconds docstring.
        self.interaction_timeout_seconds = interaction_timeout_seconds
        # Scope boundary for MechanicalCrawler's URL frontier - a link (or a
        # redirect a click lands on) that leaves this crawl's own site is out
        # of scope and never itself visited, even though the interaction/edge
        # that led there is still recorded. See MechanicalCrawler's own
        # base_url/allow_subdomains docstring and src/utils/urls.py's
        # is_in_scope() for what "same site" means here.
        self.allow_subdomains = allow_subdomains
        self.tree_ascii = tree_ascii
        self.max_passes_per_page = max_passes_per_page
        self.max_visits_per_route_shape = max_visits_per_route_shape
        # False skips the per-fillable-field AI call entirely (falls back to
        # MechanicalCrawler's fast deterministic placeholder) - the AI call
        # is a real network+generation round trip per field (more so for a
        # remote/local model), worth cutting for a speed-focused run that
        # doesn't need realistic fill values in the output.
        self.ai_fill_values = ai_fill_values
        # How many pages MechanicalCrawler.crawl_site visits concurrently.
        # Default 1 keeps the original fully-sequential behavior - see
        # MechanicalCrawler's own docstring for what raising this actually
        # changes and its tradeoffs.
        self.page_concurrency = page_concurrency
        # Storage-side knobs (docs/explicativos/plan-almacenamiento.md Fase A) -
        # see debug_logs_keep_last/export_json's own docstrings on
        # PragmaConfig for what each does and why both default to "off"/
        # "unbounded" (unchanged prior behavior).
        self.debug_logs_keep_last = debug_logs_keep_last
        self.export_json = export_json
        # Pages per GraphPRDSynthesizer batch-summarize call - see PragmaConfig.
        # prd_synth_batch_size's docstring for what this fixes and why.
        self.prd_synth_batch_size = prd_synth_batch_size

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
            # No-op for InMemoryGraphStore (nothing persists across runs there
            # anyway) - matters for graph_store: neo4j, see PragmaConfig.fresh's
            # docstring for why this defaults to on.
            graph_store.clear_site(site)

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
            page_timeout_seconds=config.page_timeout_seconds,
            prefetch=config.prefetch,
            block_images=config.block_images,
            allow_subdomains=config.allow_subdomains,
            debug_logs_keep_last=config.debug_logs_keep_last,
            export_json=config.export_json,
            prd_synth_batch_size=config.prd_synth_batch_size,
            interaction_timeout_seconds=config.interaction_timeout_seconds,
        )

    def run(self, url: str) -> EngineRunResult:
        """Crawl `url`, synthesize its PRD and component tree, write both,
        and return their output paths.

        Synchronous entry point (unchanged shape for the CLI) bridging to the
        async crawl underneath via `asyncio.run` - crawl4ai owns an async
        browser lifecycle, but nothing above `Engine` needs to know that.
        """
        return asyncio.run(self._run_async(url))

    async def _run_async(self, url: str) -> EngineRunResult:
        site = self.site or urlparse(url).netloc
        sink = GraphStoreSink(self.graph_store, site)

        debug_log: Optional[CrawlDebugLog] = None
        if self.debug_logs_dir:
            run_dir = f"{self.debug_logs_dir}/{_slugify(url)}_{_timestamp()}"
            debug_log = CrawlDebugLog(run_dir, site=site)

        async with Crawl4AICrawler(
            headless=self.headless,
            wait_seconds=self.wait_seconds,
            interaction_wait_seconds=self.interaction_wait_seconds,
            debug_log=debug_log,
            page_timeout_seconds=self.page_timeout_seconds,
            prefetch=self.prefetch,
            block_images=self.block_images,
            interaction_timeout_seconds=self.interaction_timeout_seconds,
        ) as crawler:
            fill_value_fn = (
                make_ai_fill_value_fn(self.agent) if self.ai_fill_values else default_placeholder_fill_value
            )
            mechanical = MechanicalCrawler(
                crawler,
                sink=sink,
                element_budget=self.element_budget,
                fill_value_fn=fill_value_fn,
                max_pages=self.max_pages,
                max_passes_per_page=self.max_passes_per_page,
                max_visits_per_route_shape=self.max_visits_per_route_shape,
                page_concurrency=self.page_concurrency,
                base_url=url,
                allow_subdomains=self.allow_subdomains,
            )
            await mechanical.crawl_site(url)

        if debug_log:
            debug_log.close()
            # Prune only after close() - never delete a directory a live
            # CrawlDebugLog handle might still write to. No-op unless
            # debug_logs_keep_last is set (see its own docstring).
            prune_old_runs(self.debug_logs_dir, _slugify(url), self.debug_logs_keep_last)

        run_timestamp = _timestamp()
        synthesizer = GraphPRDSynthesizer(self.agent, self.graph_store, batch_size=self.prd_synth_batch_size)
        prd = synthesizer.synthesize(site)
        prd_path = f"{self.out_dir}/{_slugify(url)}_prd_{run_timestamp}.md"
        write_output(prd_path, prd)

        tree_doc = generate_component_tree_document(self.graph_store, site, use_box_drawing=not self.tree_ascii)
        tree_path = f"{self.out_dir}/{_slugify(url)}_tree_{run_timestamp}.md"
        write_output(tree_path, tree_doc)

        export_path: Optional[str] = None
        if self.export_json:
            export_doc = generate_graph_export_document(self.graph_store, site)
            export_path = f"{self.out_dir}/{_slugify(url)}_graph_{run_timestamp}.json"
            write_output(export_path, export_doc)

        finished_pages, total_pages = self.graph_store.count_visited(site)
        unexplored_components, total_components = self.graph_store.count_unexplored_components(site)
        manifest_path = record_run_manifest(
            self.out_dir,
            site,
            {
                "timestamp": run_timestamp,
                "url": url,
                "graph_store": self.graph_store.__class__.__name__,
                "prd_path": prd_path,
                "tree_path": tree_path,
                "export_path": export_path,
                "pages_finished": finished_pages,
                "pages_total": total_pages,
                "components_total": total_components,
                "components_unexplored": unexplored_components,
            },
        )

        # Regenerated unconditionally on every run, same as the manifest
        # itself - cheap (one JSON parse + a Markdown string build over
        # whatever's already in runs.json), and always reflects reality
        # rather than needing a separate "please re-index" step.
        index_doc = generate_docs_index(self.out_dir)
        index_path = f"{self.out_dir}/index.md"
        write_output(index_path, index_doc)

        self.graph_store.close()
        return EngineRunResult(
            prd_path=prd_path,
            tree_path=tree_path,
            export_path=export_path,
            manifest_path=manifest_path,
            index_path=index_path,
        )
