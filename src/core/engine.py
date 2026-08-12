"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.
Details: docs/dev/core/engine.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from ..crawlers.crawl4ai_crawler import Crawl4AICrawlerConfig
from ..crawlers.crawl4ai_crawler_pool import Crawl4AICrawlerPool
from ..crawlers.debug_log import CrawlDebugLog, prune_old_runs
from ..crawlers.fill_value_agent import make_ai_fill_value_fn
from ..crawlers.fill_values import default_placeholder_fill_value
from ..crawlers.graph_sink import GraphStoreSink
from ..crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from ..generators.component_family import (
    build_component_families,
    label_for_tag,
    tags_with_multiple_instances,
)
from ..generators.component_family_narrator import narrate_family_purposes
from ..generators.component_tree import generate_component_tree_document
from ..generators.graph_export import generate_graph_export_document
from ..generators.graph_prd_synthesizer import GraphPRDSynthesizer
from ..generators.request_family import build_inferred_requests
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


def _apply_component_families(graph_store: GraphStore, site: str, agent: Agent) -> None:
    """Post-hoc, whole-site pass: infer reusable component families, give
    each a one-sentence LLM-narrated purpose, and add per-tag Neo4j
    labels - all from what the crawl just discovered, then write it back.
    Runs once, after the crawl finishes - family clustering needs to see
    every discovered component at once, not the live per-page write
    stream `MechanicalCrawler` produces during the crawl.

    Args:
        graph_store: the same `GraphStore` the just-finished crawl wrote
            to - read back from here (`get_component_ledger`), then
            written back to (`record_component_families`,
            `apply_tag_labels`).
        site: which site's just-crawled data to process.
        agent: the same LLM backend used for PRD narration - passed
            through to `narrate_family_purposes` for the one-sentence
            "what is this pattern used for" description each family gets.

    Returns:
        None. Four steps, always in this order:
        1. Read every discovered component for `site` via
           `get_component_ledger`, and flatten its `{page_url: {path:
           {...}}}` nesting into one flat list of dicts (each with
           `page_url` and `path` folded in) - the shape
           `component_family.build_component_families`/
           `tags_with_multiple_instances` both expect. The ledger's
           per-page nesting exists for `GraphPRDSynthesizer`'s
           page-by-page narration, not for a whole-site pass like this
           one.
        2. `build_component_families` clusters that flat list into
           `ComponentFamily` objects (see that function's own docstring
           for the full algorithm) - `purpose` is still `""` on every one
           at this point, since clustering itself never calls the model.
        3. `narrate_family_purposes` fills in `purpose`, one
           `agent.generate()` call per family that has any member text at
           all - see that function's own docstring for its graceful-
           degradation behavior on a single family's failure.
        4. The narrated families are written via `record_component_
           families` (a full rebuild of `site`'s family structure every
           call, per that method's own contract), and
           `tags_with_multiple_instances` picks which raw HTML tags
           appear often enough to deserve their own Neo4j label, each
           mapped through `label_for_tag` to its actual label string
           (e.g. `"button"` -> `"Button"`), written via
           `apply_tag_labels`.
    Details: docs/dev/core/engine.md#_apply_component_families
    """
    ledger = graph_store.get_component_ledger(site)
    components = [
        {"page_url": page_url, "path": path, **record}
        for page_url, page_components in ledger.items()
        for path, record in page_components.items()
    ]
    families = build_component_families(components)
    member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
    families = narrate_family_purposes(agent, families, member_texts)
    graph_store.record_component_families(site, families)

    tags = tags_with_multiple_instances(components)
    graph_store.apply_tag_labels(site, {tag: label_for_tag(tag) for tag in tags})


def _apply_request_graph(graph_store: GraphStore, site: str) -> None:
    """Post-hoc, whole-site pass: infer distinct API endpoints (and which
    Components trigger each one) from network requests already captured
    on Component nodes, then write them back. Independent of - and reads
    the graph a second time from - `_apply_component_families`, rather
    than sharing its already-flattened `components` list: this keeps the
    two passes fully separable (one about component *look-alikes*, this
    one about *endpoint* identity), at the cost of one extra
    `get_component_ledger` read per crawl - a single local read, not a
    hot path, run once per whole crawl.

    Args:
        graph_store: same `GraphStore` the crawl wrote to.
        site: which site's just-crawled data to process.

    Returns:
        None. Reads every discovered component's `network_requests` via
        `get_component_ledger`, flattens the same way
        `_apply_component_families` does, clusters them via
        `request_family.build_inferred_requests` (see that function's own
        docstring), and writes the result via `record_inferred_requests`
        - a full rebuild of `site`'s inferred-request structure every
        call, same contract as `record_component_families`.
    Details: docs/dev/core/engine.md#_apply_request_graph
    """
    ledger = graph_store.get_component_ledger(site)
    components = [
        {"page_url": page_url, "path": path, **record}
        for page_url, page_components in ledger.items()
        for path, record in page_components.items()
    ]
    graph_store.record_inferred_requests(site, build_inferred_requests(components))


def _resolve_pool_size(browser_pool_size: Optional[int], page_concurrency: int) -> int:
    """How many real Chromium processes Crawl4AICrawlerPool should launch.
    Unset ties it to page_concurrency (one dedicated browser per worker);
    set, it's clamped so no pool member ever sits idle with no worker
    routed to it. Details: docs/dev/core/engine.md#_resolve_pool_size
    """
    if browser_pool_size is None:
        return page_concurrency
    return min(browser_pool_size, page_concurrency)


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
                ),
            )
            await mechanical.crawl_site(url)

        if debug_log:
            await debug_log.close()
            # Prune only after close() - see prune_old_runs's own doc.
            prune_old_runs(self.debug_logs_dir, _slugify(url), self.debug_logs_keep_last)

        # Whole-site passes, after every component the crawl found is
        # already in the graph - must run before synthesis reads it below.
        _apply_component_families(self.graph_store, site, self.agent)
        _apply_request_graph(self.graph_store, site)

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
