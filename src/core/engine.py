"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.
Details: docs/dev/core/engine.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from ..crawlers.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from ..crawlers.debug_log import CrawlDebugLog, prune_old_runs
from ..crawlers.fill_value_agent import make_ai_fill_value_fn
from ..crawlers.fill_values import default_placeholder_fill_value
from ..crawlers.graph_sink import GraphStoreSink
from ..crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
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
    """`Engine.run()`'s return value - the output documents from one crawl.
    Details: docs/dev/core/engine.md#enginerunresult
    """

    prd_path: str
    tree_path: str
    export_path: Optional[str] = None
    manifest_path: str = ""
    # Browsable Markdown index of every run, regenerated fresh every run.
    # Details: docs/dev/core/engine.md#enginerunresult-index_path
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
        # See PragmaConfig / Crawl4AICrawlerConfig for what each changes.
        # Details: docs/dev/core/engine.md#__init__-crawl-timeouts
        self.page_timeout_seconds = page_timeout_seconds
        self.prefetch = prefetch
        self.block_images = block_images
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
        self.debug_logs_keep_last = debug_logs_keep_last
        self.export_json = export_json
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
            interaction_timeout_seconds=self.interaction_timeout_seconds,
        )
        async with Crawl4AICrawler(crawler_config) as crawler:
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
                ),
            )
            await mechanical.crawl_site(url)

        if debug_log:
            debug_log.close()
            # Prune only after close() - see prune_old_runs's own doc.
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

        # Regenerated unconditionally, same as the manifest itself - cheap.
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
