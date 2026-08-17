"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.
Details: docs/dev/core/engine.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.browser.debug_log import CrawlDebugLog, prune_old_runs
from spiders.content.fill_value_agent import make_ai_fill_value_fn
from spiders.content.fill_values import default_placeholder_fill_value
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import CrawlBudget, MechanicalCrawler, MechanicalCrawlerConfig
from generators.component_family import build_component_families
from generators.component_family_narrator import family_signature, narrate_family_purposes
from generators.ledger import flat_component_ledger
from generators.pipeline import DocumentNaming, run_document_pipeline
from generators.request_family import build_inferred_requests
from analysis.graph_projection import project_graph
from utils.io import generate_docs_index, record_run_manifest, write_output
from utils.urls import route_shape, slugify
from .caching_graph_store import CachingGraphStore
from .config import PragmaConfig
from .documents import DocumentRequest, ProducedDocument
from .interfaces import Agent, GraphStore
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def _timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _apply_component_families(graph_store: GraphStore, site: str, agent: Agent) -> None:
    """Post-hoc, whole-site pass: infer reusable component families, give
    each a one-sentence LLM-narrated purpose, then write it back. Runs
    once, after the crawl finishes - family clustering needs to see
    every discovered component at once, not the live per-page write
    stream `MechanicalCrawler` produces during the crawl.

    Args:
        graph_store: the same `GraphStore` the just-finished crawl wrote
            to - read back from here (`get_component_ledger`), then
            written back to (`record_component_families`).
        site: which site's just-crawled data to process.
        agent: the same LLM backend used for PRD narration - passed
            through to `narrate_family_purposes` for the one-sentence
            "what is this pattern used for" description each family gets.

    Returns:
        None. Three steps, always in this order:
        1. Read every discovered component for `site` via
           `ledger.flat_component_ledger` - see that function for why the
           ledger's per-page nesting has to be flattened for a whole-site
           pass like this one.
        2. `build_component_families` clusters that flat list into
           `ComponentFamily` objects (see that function's own docstring
           for the full algorithm) - `purpose` is still `""` on every one
           at this point, since clustering itself never calls the model.
        3. `narrate_family_purposes` fills in `purpose`, one
           `agent.generate()` call per family that has any member text at
           all - see that function's own docstring for its graceful-
           degradation behavior on a single family's failure - and the
           narrated families are written via `record_component_families`
           (a full rebuild of `site`'s family structure every call, per
           that method's own contract).
    Details: docs/dev/core/engine.md#_apply_component_families
    """
    components = flat_component_ledger(graph_store, site)
    families = build_component_families(components)
    print(f"Grouped {len(components)} components into {len(families)} families.")
    member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
    # Read before record_component_families wipes them: a family whose members
    # did not change keeps its sentence rather than buying it again, which is
    # what keeps a site crawled in short resumable passes from re-narrating
    # everything every pass. Details: docs/dev/core/engine.md#known-purposes
    known_purposes = {
        family_signature(existing): existing.purpose
        for existing in graph_store.get_component_families(site)
        if existing.purpose
    }
    families = narrate_family_purposes(agent, families, member_texts, known_purposes)
    graph_store.record_component_families(site, families)


def _apply_request_graph(graph_store: GraphStore, site: str) -> None:
    """Post-hoc, whole-site pass: infer distinct API endpoints (and which
    Components trigger each one) from network requests already captured
    on Component nodes, then write them back. Independent of - and reads
    the graph a second time from - `_apply_component_families`, rather
    than sharing its already-flattened component list: this keeps the
    two passes fully separable (one about component *look-alikes*, this
    one about *endpoint* identity), at the cost of one extra
    `get_component_ledger` read per crawl - a single local read, not a
    hot path, run once per whole crawl.

    Args:
        graph_store: same `GraphStore` the crawl wrote to.
        site: which site's just-crawled data to process.

    Returns:
        None. Reads every discovered component's `network_requests` via
        `ledger.flat_component_ledger`, clusters them via
        `request_family.build_inferred_requests` (see that function's own
        docstring), and writes the result via `record_inferred_requests`
        - a full rebuild of `site`'s inferred-request structure every
        call, same contract as `record_component_families`.
    Details: docs/dev/core/engine.md#_apply_request_graph
    """
    components = flat_component_ledger(graph_store, site)
    page_requests = graph_store.get_page_network_ledger(site)
    graph_store.record_inferred_requests(site, build_inferred_requests(components, page_requests))


def _apply_graph_projection(graph_store: GraphStore, site: str, root: str) -> None:
    """Post-hoc, whole-site pass: materialize the navigation graph into
    `networkx` and write back per-page metrics and module assignments -
    Storage Phase 7. Independent of the two passes above (reads only
    `get_edges`, not the component ledger), so it can run in any order
    relative to them.

    Args:
        graph_store: same `GraphStore` the crawl wrote to.
        site: which site's just-crawled data to process.
        root: the crawl's own start URL, `route_shape`d to match every
            other page key in the graph - `project_graph`'s `click_depth`
            is BFS distance from here.

    Returns:
        None. `project_graph` (`analysis/graph_projection.py`) computes
        in/out degree, click depth, betweenness, PageRank, articulation
        points, and Louvain module assignment; results are written via
        `record_page_metrics`/`record_page_modules` - full rebuilds, same
        contract as `record_component_families`.
    Details: docs/dev/core/engine.md#_apply_graph_projection
    """
    result = project_graph(graph_store.get_edges(site), root=root)
    graph_store.record_page_metrics(site, [m.as_dict() for m in result.metrics])
    graph_store.record_page_modules(site, [m.as_dict() for m in result.modules])
    if result.cycles:
        print(f"Graph projection: {len(result.cycles)} navigation cycle(s) found.")


@dataclass
class EngineRunResult:
    """`Engine.run()`'s return value - the output documents from one crawl.
    Details: docs/dev/core/engine.md#enginerunresult
    """

    prd_path: str
    tree_path: str
    export_path: Optional[str] = None
    # The "Start Here" index of everything this run produced; always written.
    # Details: docs/dev/core/engine.md#enginerunresult-master_path
    master_path: str = ""
    # Every document this run wrote, in pipeline order, master last. The
    # named fields above are the pre-existing shortcuts into this list -
    # this is what a caller iterates so it doesn't need a branch per
    # document. Details: docs/dev/core/engine.md#enginerunresult-documents
    documents: Tuple[ProducedDocument, ...] = ()
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
        out_dir: str = "data/output",
        site: str = "",
        max_pages: Optional[int] = None,
        crawl_budget: Optional[CrawlBudget] = None,
        headless: bool = True,
        wait_seconds: float = 1.0,
        interaction_wait_seconds: Optional[float] = None,
        debug_logs_dir: str = "data/debug_logs",
        tree_ascii: bool = False,
        max_visits_per_route_shape: int = 1,
        ai_fill_values: bool = True,
        page_concurrency: int = 4,
        page_timeout_seconds: float = 15.0,
        prefetch: bool = False,
        block_images: bool = True,
        allow_subdomains: bool = False,
        debug_logs_keep_last: Optional[int] = None,
        export_json: bool = False,
        prd_synth_batch_size: int = 5,
        interaction_timeout_seconds: Optional[float] = 10.0,
        documents: Optional[List[str]] = None,
    ) -> None:
        self.agent = agent
        self.graph_store = graph_store
        self.out_dir = out_dir
        self.site = site
        self.max_pages = max_pages
        self.crawl_budget = crawl_budget or CrawlBudget()
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
        self.max_visits_per_route_shape = max_visits_per_route_shape
        # False skips the per-fillable-field AI call entirely.
        # Details: docs/dev/core/engine.md#__init__-ai_fill_values
        self.ai_fill_values = ai_fill_values
        self.page_concurrency = page_concurrency  # see MechanicalCrawler's own docstring
        self.debug_logs_keep_last = debug_logs_keep_last
        self.export_json = export_json
        self.prd_synth_batch_size = prd_synth_batch_size
        # None keeps PragmaConfig's own default rather than duplicating the
        # list here - see docs/dev/core/config.md#documents.
        self.documents = documents if documents is not None else list(PragmaConfig().documents)

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
            max_pages=config.max_pages,
            crawl_budget=CrawlBudget(**config.crawl_budget),
            headless=config.headless,
            wait_seconds=config.wait_seconds,
            interaction_wait_seconds=config.interaction_wait_seconds,
            debug_logs_dir=config.debug_logs_dir,
            tree_ascii=config.tree_ascii,
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
            documents=config.documents,
        )

    def run(self, url: str) -> EngineRunResult:
        """Crawl `url`, synthesize its PRD and component tree, write both.
        Details: docs/dev/core/engine.md#run
        """
        return asyncio.run(self._run_async(url))

    async def _run_async(self, url: str) -> EngineRunResult:
        site = self.site or urlparse(url).netloc
        # One id for this whole crawl, stamped onto every edge it writes
        # (GraphStoreSink.record_navigation_edge) so a later run can tell
        # "this transition first appeared in run X, last seen in run Y"
        # apart from one that's been stable since the first crawl. Distinct
        # from `run_timestamp` below (generated after the crawl, for
        # document/manifest filenames) - this one has to exist before the
        # crawl starts, since writes need it as they happen.
        run_id = _timestamp()
        # Same base_url/allow_subdomains the frontier gates on, so a link is
        # judged in-scope identically whether it is queued or recorded.
        # Details: docs/dev/core/engine.md#sink-scope
        sink = GraphStoreSink(
            self.graph_store, site, base_url=url, allow_subdomains=self.allow_subdomains, run_id=run_id,
        )

        debug_log: Optional[CrawlDebugLog] = None
        if self.debug_logs_dir:
            run_dir = f"{self.debug_logs_dir}/{slugify(url)}_{_timestamp()}"
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
                    fill_value_fn=fill_value_fn,
                    max_pages=self.max_pages,
                    budget=self.crawl_budget,
                    max_visits_per_route_shape=self.max_visits_per_route_shape,
                    page_concurrency=self.page_concurrency,
                    base_url=url,
                    allow_subdomains=self.allow_subdomains,
                ),
            )
            await mechanical.crawl_site(url)
            # Read before the crawler goes out of scope: the documents
            # below have to say whether they describe a whole site or one
            # budgeted slice of it.
            # Details: docs/dev/core/engine.md#stopped_reason
            stopped_reason = mechanical.stopped_reason or ""

        if debug_log:
            await debug_log.close()
            # Prune only after close() - see prune_old_runs's own doc.
            prune_old_runs(self.debug_logs_dir, slugify(url), self.debug_logs_keep_last)

        # Whole-site passes, after every component the crawl found is
        # already in the graph - must run before synthesis reads it below.
        # Each phase announces itself: everything from here to the last
        # written document used to run silent, which made a long run
        # indistinguishable from a hung one.
        # Details: research/plan-progreso-en-terminal.md
        #
        # graph_store (not self.graph_store) from here on: the crawl has
        # finished writing, so every whole-site read from here to the end
        # of the pipeline is safe to memoize per (method, site) -
        # get_component_ledger alone was called ~8 times per run before
        # this, once per generator that needed it. See
        # CachingGraphStore's own module docstring for why this is safe
        # specifically *here* (after the crawl, not during it) and not a
        # general-purpose cache. self.graph_store itself is untouched, so
        # self.graph_store.close() below still closes the real connection.
        graph_store = CachingGraphStore(self.graph_store)
        print("\nCrawl finished. Grouping components into families...")
        _apply_component_families(graph_store, site, self.agent)
        print("Inferring API endpoints from captured requests...")
        _apply_request_graph(graph_store, site)
        print("Projecting the navigation graph into modules and metrics...")
        _apply_graph_projection(graph_store, site, route_shape(url))

        run_timestamp = _timestamp()
        request = DocumentRequest(
            graph_store=graph_store,
            site=site,
            agent=self.agent,
            settings={
                "prd_synth_batch_size": self.prd_synth_batch_size,
                "tree_ascii": self.tree_ascii,
                "stopped_reason": stopped_reason,
            },
        )
        naming = DocumentNaming(out_dir=self.out_dir, slug=slugify(url), timestamp=run_timestamp)
        produced = run_document_pipeline(request, naming, self._document_names())
        paths = {document.name: document.path for document in produced}

        print("Writing run manifest and index...")

        finished_pages, total_pages = self.graph_store.count_visited(site)
        unexplored_components, total_components = self.graph_store.count_unexplored_components(site)
        manifest_path = record_run_manifest(
            self.out_dir,
            site,
            {
                "timestamp": run_timestamp,
                "url": url,
                "graph_store": self.graph_store.__class__.__name__,
                "prd_path": paths.get("prd"),
                "tree_path": paths.get("tree"),
                "export_path": paths.get("export"),
                "master_path": paths.get("master"),
                "document_paths": {document.name: document.path for document in produced},
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
            prd_path=paths.get("prd", ""),
            tree_path=paths.get("tree", ""),
            export_path=paths.get("export"),
            master_path=paths.get("master", ""),
            documents=tuple(produced),
            manifest_path=manifest_path,
            index_path=index_path,
        )

    def _document_names(self) -> List[str]:
        """Which documents this run generates: the configured list, plus
        "export" when the standalone `export_json` flag is on and the list
        didn't already ask for it. The flag predates `PragmaConfig.documents`
        and stays honored so an existing pragma.yaml keeps working.
        Details: docs/dev/core/engine.md#_document_names
        """
        names = list(self.documents)
        if self.export_json and "export" not in names:
            names.append("export")
        return names
