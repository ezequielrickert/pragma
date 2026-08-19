"""The `pragma docs` entry point: docs-only generation from an existing
site DB, no re-crawl.

Deliberately its own class, not a mode on `Engine` - `Engine._run_async`
always drives a `MechanicalCrawler` crawl first, and `MechanicalCrawler.
crawl_site` always navigates, even against a fully-crawled DB (there is
no "just read what's there" mode). `pragma docs` sidesteps that gap
entirely rather than fixing it: it never touches `Crawl4AICrawler` or
`MechanicalCrawler` at all, only the graph store `pragma static` (and,
if they ran, `pragma cluster`/`pragma dynamic`) already wrote. Absorbs
`analysis/graph_projection_apply.py::apply_graph_projection` as its own
first internal step, since nothing but doc generation consumes
projection output.
Details: docs/dev/core/docs_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from analysis.graph_projection_apply import apply_graph_projection
from generators.pipeline import DocumentNaming, run_document_pipeline
from utils.io import generate_docs_index, record_run_manifest, write_output
from utils.urls import slugify
from .caching_graph_store import CachingGraphStore
from .config import PragmaConfig
from .documents import DocumentRequest, ProducedDocument
from .interfaces import Agent
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class DocsRunResult:
    """`DocsEngine.run()`'s return value - the output documents from one
    docs-only pass. Details: docs/dev/core/docs_engine.md#docsrunresult
    """

    site: str
    documents: Tuple[ProducedDocument, ...] = ()
    manifest_path: str = ""
    index_path: str = ""


class DocsEngine:
    """Wires an agent and a graph store, then generates documents from
    whatever that store already holds. Details: docs/dev/core/docs_engine.md#docsengine
    """

    def __init__(
        self,
        agent: Agent,
        graph_store: Any,
        site: str,
        out_dir: str = "data/output",
        tree_ascii: bool = False,
        prd_synth_batch_size: int = 5,
        export_json: bool = False,
        documents: Optional[List[str]] = None,
    ) -> None:
        self.agent = agent
        self.graph_store = graph_store
        self.site = site
        self.out_dir = out_dir
        self.tree_ascii = tree_ascii
        self.prd_synth_batch_size = prd_synth_batch_size
        self.export_json = export_json
        self.documents = documents if documents is not None else list(PragmaConfig().documents)

    @classmethod
    def from_config(cls, config: PragmaConfig, site: str) -> "DocsEngine":
        """Resolve the agent and graph store named in `config`, scoped to
        `site` - a bare host/slug, not a URL, since `pragma docs` reads
        an existing site a previous `pragma static` run already wrote
        rather than crawling one of its own. Same convention
        `ClusterEngine.from_config` uses.
        Details: docs/dev/core/docs_engine.md#from_config
        """
        provider_options = config.agents.get(config.agent, {})
        try:
            agent = AGENT_REGISTRY.create(config.agent, **provider_options)
        except Exception as exc:
            print(f"Failed to initialize {config.agent} agent: {exc}; falling back to mock")
            agent = AGENT_REGISTRY.create("mock")

        store_options = config.graph_stores.get(config.graph_store, {})
        graph_store = GRAPH_STORE_REGISTRY.create(config.graph_store, site=site, **store_options)
        graph_store.connect()

        return cls(
            agent,
            graph_store,
            site,
            out_dir=config.out_dir,
            tree_ascii=config.tree_ascii,
            prd_synth_batch_size=config.prd_synth_batch_size,
            export_json=config.export_json,
            documents=config.documents,
        )

    def run(self) -> DocsRunResult:
        """Project the navigation graph, then generate every configured
        document from `site`'s existing graph store - no crawling.
        Works against a `static`-only DB: nothing here reads component
        families or the semantic tier, so `pragma cluster`/`pragma
        dynamic` having run is a richer input, not a requirement.
        Details: docs/dev/core/docs_engine.md#run
        """
        finished_pages, total_pages = self.graph_store.count_visited()
        if total_pages == 0:
            print(
                f"Warning: {self.site} has no pages recorded in this graph store - "
                "did you run `pragma static` first, or point --graph-store at the right backend?"
            )
        unexplored_components, total_components = self.graph_store.count_unexplored_components()

        # CachingGraphStore from here on, same discipline as Engine._run_async:
        # every whole-site read below is safe to memoize per method once
        # nothing is still writing. Details: docs/dev/core/engine.md#run
        graph_store = CachingGraphStore(self.graph_store)
        print("Projecting the navigation graph into modules and metrics...")
        apply_graph_projection(graph_store, self.site)

        run_timestamp = _timestamp()
        request = DocumentRequest(
            graph_store=graph_store,
            site=self.site,
            agent=self.agent,
            settings={
                "prd_synth_batch_size": self.prd_synth_batch_size,
                "tree_ascii": self.tree_ascii,
                # No crawl happened in this process, so there is no
                # partial-run reason to report - unlike Engine's own
                # stopped_reason, always "" here.
                "stopped_reason": "",
            },
        )
        naming = DocumentNaming(out_dir=self.out_dir, slug=slugify(self.site), timestamp=run_timestamp)
        produced = run_document_pipeline(request, naming, self._document_names())
        paths = {document.name: document.path for document in produced}

        manifest_path = record_run_manifest(
            self.out_dir,
            self.site,
            {
                "timestamp": run_timestamp,
                "url": self.site,
                "graph_store": self.graph_store.__class__.__name__,
                "prd_path": paths.get("prd"),
                "tree_path": paths.get("tree"),
                "export_path": paths.get("export"),
                "master_path": paths.get("master"),
                "document_paths": paths,
                "pages_finished": finished_pages,
                "pages_total": total_pages,
                "components_total": total_components,
                "components_unexplored": unexplored_components,
            },
        )

        index_doc = generate_docs_index(self.out_dir)
        index_path = f"{self.out_dir}/index.md"
        write_output(index_path, index_doc)

        self.graph_store.close()
        return DocsRunResult(
            site=self.site, documents=tuple(produced), manifest_path=manifest_path, index_path=index_path,
        )

    def _document_names(self) -> List[str]:
        """Same contract as `Engine._document_names`.
        Details: docs/dev/core/docs_engine.md#_document_names
        """
        names = list(self.documents)
        if self.export_json and "export" not in names:
            names.append("export")
        return names
