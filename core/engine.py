"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one crawl+synthesize job.
Details: docs/dev/core/engine.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from urllib.parse import urlparse

from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.browser.debug_log import CrawlDebugLog, prune_old_runs
from spiders.content.fill_value_agent import make_ai_fill_value_fn
from spiders.content.fill_values import default_placeholder_fill_value
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import CrawlBudget, MechanicalCrawler, MechanicalCrawlerConfig
from dashboard.shell import DashboardRunContext, KpiContext, write_dashboard
from generators.data_model import build_entities
from generators.ledger import flat_component_ledger
from generators.pipeline import DocumentNaming, run_document_pipeline
from analysis.component_matching_pipeline import apply_component_matching
from analysis.graph_projection_apply import apply_graph_projection
from utils.io import generate_docs_index, record_run_manifest, write_output
from utils.urls import route_shape, slugify
from .caching_graph_store import CachingGraphStore
from .config import PragmaConfig
from .documents import DocumentRequest, ProducedDocument
from .graph_store_resolution import resolve_graph_store
from .interfaces import Agent
from .registry import AGENT_REGISTRY


def _timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _apply_data_model(graph_store: Any, run_id: str) -> None:
    """Post-hoc, whole-site pass: deduce the semantic tier's `Entity`/`Field`
    set from the forms the crawl found, and write it back with its provenance.

    Whole-site rather than per-page for the same reason family clustering is:
    the derivation groups components by the form they sit in, and a live
    per-page write stream cannot see a form whose inputs arrived across two
    visits.

    Args:
        graph_store: same store the crawl wrote to.
        run_id: stamped onto every `DERIVED_FROM` edge, so a reader can tell
            which run concluded what.

    Returns:
        None. `record_entities` refuses any node with no provenance, which is
        why this pass has no error handling of its own: a raise here means the
        derivation produced an unsupported assertion, and that is a bug to
        fix rather than a document to degrade.
    Details: docs/dev/core/engine.md#_apply_data_model
    """
    entities = build_entities(flat_component_ledger(graph_store))
    field_count = sum(len(entity.fields) for entity in entities)
    print(f"Deduced {len(entities)} entity/entities with {field_count} field(s) from forms.")
    graph_store.record_entities(entities, run_id=run_id)


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
    # Phase C's own entry point (ADR-0016 point 4, ticket #125) - the
    # file to open in a browser, distinct from index_path's cross-run
    # Markdown index. Details: docs/dev/core/engine.md#enginerunresult-dashboard_path
    dashboard_path: str = ""


class Engine:
    """Wires an agent and a graph store, then crawls a URL and synthesizes its PRD."""

    def __init__(
        self,
        agent: Agent,
        graph_store: Any,
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
        navigation_watchdog_seconds: float = 60.0,
        session_cleanup_timeout_seconds: float = 10.0,
        prefetch: bool = False,
        block_images: bool = True,
        allow_subdomains: bool = False,
        debug_logs_keep_last: Optional[int] = None,
        export_json: bool = False,
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
        self.navigation_watchdog_seconds = navigation_watchdog_seconds
        self.session_cleanup_timeout_seconds = session_cleanup_timeout_seconds
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

        # Computed before the store: LadybugGraphStore is site-scoped at
        # construction (one database per site), unlike every backend this
        # replaces, which took `site` per method call instead and could be
        # built with no site known yet.
        site = urlparse(config.url).netloc if config.url else ""
        store_options = config.graph_stores.get(config.graph_store, {})
        graph_store = resolve_graph_store(config.graph_store, site, store_options)

        if config.fresh and site:
            graph_store.reset()  # see PragmaConfig.fresh

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
            navigation_watchdog_seconds=config.navigation_watchdog_seconds,
            session_cleanup_timeout_seconds=config.session_cleanup_timeout_seconds,
            prefetch=config.prefetch,
            block_images=config.block_images,
            allow_subdomains=config.allow_subdomains,
            debug_logs_keep_last=config.debug_logs_keep_last,
            export_json=config.export_json,
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
            self.graph_store, base_url=url, allow_subdomains=self.allow_subdomains, run_id=run_id,
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
            navigation_watchdog_seconds=self.navigation_watchdog_seconds,
            session_cleanup_timeout_seconds=self.session_cleanup_timeout_seconds,
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
        # apply_component_matching runs against self.graph_store directly,
        # not the CachingGraphStore constructed below - it merges rows
        # (merge_components/merge_containers) partway through its own four
        # steps, then re-reads get_component_ledger/get_container_forest
        # to see the result. CachingGraphStore's safety argument is that
        # nothing it wraps writes what it caches; this pass is the one
        # exception to that, so it has to run before the wrapper exists,
        # not through it.
        print("\nCrawl finished. Matching and collapsing reused components...")
        apply_component_matching(self.graph_store, self.agent)

        # graph_store (not self.graph_store) from here on: every remaining
        # whole-site read is safe to memoize per method -
        # get_component_ledger alone was called ~8 times per run before
        # this, once per generator that needed it. See
        # CachingGraphStore's own module docstring for why this is safe
        # specifically *here* (after both the crawl and the matching pass
        # above) and not a general-purpose cache. self.graph_store itself
        # is untouched, so self.graph_store.close() below still closes the
        # real connection.
        graph_store = CachingGraphStore(self.graph_store)
        print("Projecting the navigation graph into modules and metrics...")
        apply_graph_projection(graph_store, route_shape(url))
        print("Deducing the data model from the forms found...")
        _apply_data_model(graph_store, run_id)

        run_timestamp = _timestamp()
        # `run_id`, not `run_timestamp`: coverage.json's own run_id (ADR-0001)
        # should match the identifier already stamped onto the graph's own
        # edges, not the separate, slightly-later timestamp used for
        # filenames - a document citing "which run produced this" wants the
        # same id the graph itself would answer with.
        duration_s = (
            datetime.now(timezone.utc)
            - datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        ).total_seconds()
        request = DocumentRequest(
            graph_store=graph_store,
            site=site,
            agent=self.agent,
            settings={
                "tree_ascii": self.tree_ascii,
                "stopped_reason": stopped_reason,
                "run_id": run_id,
                "target": url,
                "duration_s": duration_s,
            },
        )
        naming = DocumentNaming(out_dir=self.out_dir, slug=slugify(url), timestamp=run_timestamp)
        produced = run_document_pipeline(request, naming, self._document_names())
        paths = {document.name: document.path for document in produced}

        print("Writing run manifest and index...")

        finished_pages, total_pages = self.graph_store.count_visited()
        unexplored_components, total_components = self.graph_store.count_unexplored_components()
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

        kpi_context = KpiContext(
            pages_finished=finished_pages, pages_total=total_pages,
            components_explored=total_components - unexplored_components, components_total=total_components,
        )
        dashboard_context = DashboardRunContext(kpi_context=kpi_context, site=site, out_dir=self.out_dir)
        dashboard_path = write_dashboard(produced, dashboard_context)

        self.graph_store.close()
        return EngineRunResult(
            prd_path=paths.get("prd", ""),
            tree_path=paths.get("tree", ""),
            export_path=paths.get("export"),
            master_path=paths.get("master", ""),
            documents=tuple(produced),
            manifest_path=manifest_path,
            index_path=index_path,
            dashboard_path=dashboard_path,
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
