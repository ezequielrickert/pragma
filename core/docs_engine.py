"""The `pragma docs` entry point: docs-only generation from an existing
site DB, no re-crawl.

Deliberately its own class, not a mode on the crawl engines - `pragma
static`/`pragma dynamic` always drive a real crawl, and neither has a
"just read what's there" mode. `pragma docs` sidesteps that gap
entirely rather than fixing it: it never touches `Crawl4AICrawler` or
either phase command's engine at all, only the graph store `pragma
static` (and, if they ran, `pragma cluster`/`pragma dynamic`) already
wrote. Absorbs `analysis/graph_projection_apply.py::apply_graph_projection`
and the semantic-tier derivation passes (`_apply_data_model`/
`_apply_rules`/`_apply_screens`/`_apply_flows`, inherited from the
retired Legacy Engine, issue #242) as its own internal steps, since
nothing but doc generation consumes either's output.
Details: docs/dev/core/docs_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from analysis.graph_projection_apply import apply_graph_projection
from dashboard.shell import DashboardRunContext, KpiContext, write_dashboard
from generators.data_model import build_entities
from generators.flows import build_flows
from generators.ledger import flat_component_ledger
from generators.pipeline import DocumentNaming, run_document_pipeline
from generators.rules import build_rules
from generators.screen_narrator import build_page_context, narrate_screens, screen_signature
from generators.screens import build_screens
from utils.io import generate_docs_index, record_run_manifest, write_output
from utils.urls import slugify
from .caching_graph_store import CachingGraphStore
from .config import PragmaConfig
from .documents import DocumentRequest, ProducedDocument
from .interfaces import Agent
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _apply_data_model(graph_store: Any, run_id: str) -> None:
    """Post-hoc, whole-site pass: deduce the semantic tier's `Entity`/`Field`
    set from the forms the crawl found, and write it back with its provenance.

    Whole-site rather than per-page for the same reason family clustering is:
    the derivation groups components by the form they sit in, and a live
    per-page write stream cannot see a form whose inputs arrived across two
    visits.

    Args:
        graph_store: same store `run()` is already projecting/reading.
        run_id: stamped onto every `DERIVED_FROM` edge, so a reader can tell
            which run concluded what.

    Returns:
        None. `record_entities` refuses any node with no provenance, which is
        why this pass has no error handling of its own: a raise here means the
        derivation produced an unsupported assertion, and that is a bug to
        fix rather than a document to degrade.
    Details: docs/dev/core/docs_engine.md#_apply_data_model
    """
    entities = build_entities(flat_component_ledger(graph_store))
    field_count = sum(len(entity.fields) for entity in entities)
    print(f"Deduced {len(entities)} entity/entities with {field_count} field(s) from forms.")
    graph_store.record_entities(entities, run_id=run_id)


def _apply_rules(graph_store: Any, run_id: str) -> None:
    """Post-hoc, whole-site pass: one `Rule` per declared single-field
    constraint, plus one per `<select>`'s declared option set
    (`generators/rules.py::build_rules`) - the semantic tier's fourth
    writer, alongside `_apply_data_model`/`_apply_screens`/`_apply_flows`.

    Must run after `_apply_data_model`: `record_rules`'s `GOVERNS(Rule->
    Field)` edge is resolved through the `Field`/`EDITS` data
    `record_entities` writes, over the same component population - see
    `database/ladybug/rule.py`'s own module docstring.

    Args:
        graph_store: same store `run()` is already projecting/reading.
        run_id: stamped onto every `DERIVED_FROM` edge, same as
            `_apply_data_model`.

    Returns:
        None. `record_rules` refuses any rule with no `derived_from`,
        which `build_rules` always sets from the constraint's own
        source component - see `_apply_data_model`'s own docstring for
        why that leaves this pass no error handling of its own.
    Details: docs/dev/core/docs_engine.md#_apply_rules
    """
    rules = build_rules(flat_component_ledger(graph_store))
    print(f"Deduced {len(rules)} rule(s) from the constraints forms declared.")
    graph_store.record_rules(rules, run_id=run_id)


def _apply_screens(graph_store: Any, agent: Agent, run_id: str) -> None:
    """Post-hoc, whole-site pass: one `Screen` per finished `Page`
    (`generators/screens.py::build_screens`), narrated with a name/purpose
    (`generators/screen_narrator.py::narrate_screens`), and written back
    with its provenance - the semantic tier's second writer, alongside
    `_apply_data_model` above.

    Args:
        graph_store: same store `run()` is already projecting/reading.
        agent: shared across every narration step in a run, same instance
            `apply_component_matching` narrates component families with
            during `pragma cluster`.
        run_id: stamped onto every `DERIVED_FROM` edge, same as
            `_apply_data_model`.

    Returns:
        None. `record_screens` refuses any screen with no `page_url`,
        which `build_screens` always sets from a real `Page.url` - see
        `_apply_data_model`'s own docstring for why that leaves this pass
        no error handling of its own.
    Details: docs/dev/core/docs_engine.md#_apply_screens
    """
    screens = build_screens(graph_store.get_progress_table_rows())
    # Read before record_screens wipes them - a screen unchanged since the
    # last run keeps its name/purpose rather than buying them again, same
    # reasoning apply_component_matching's own narration cache follows.
    known_purposes = {
        screen_signature(existing): (existing.name, existing.purpose)
        for existing in graph_store.get_screens()
        if existing.name or existing.purpose
    }
    page_context = build_page_context(graph_store.get_page_titles(), graph_store.get_page_descriptions())
    narrated = narrate_screens(agent, screens, page_context, known_purposes)
    print(f"Deduced {len(narrated)} screen(s) from the pages the crawl finished.")
    graph_store.record_screens(narrated, run_id=run_id)


def _apply_flows(graph_store: Any, run_id: str) -> None:
    """Post-hoc, whole-site pass: one `Flow` per trace the crawl walked
    (`generators/flows.py::build_flows`), written back with its provenance
    - the semantic tier's third writer, alongside `_apply_data_model` and
    `_apply_screens` above.

    No narration step, unlike `_apply_screens`: the derivation research
    (issue #186) found `Flow.name`/`goal` fully templatable, so this pass
    needs no `Agent`.

    Args:
        graph_store: same store `run()` is already projecting/reading.
        run_id: stamped onto every `DERIVED_FROM` edge, same as
            `_apply_data_model`/`_apply_screens`.

    Returns:
        None. `record_flows` refuses any flow with no `derived_from`,
        which `build_flows` always sets from the trace's own steps - see
        `_apply_data_model`'s own docstring for why that leaves this pass
        no error handling of its own.
    Details: docs/dev/core/docs_engine.md#_apply_flows
    """
    components = flat_component_ledger(graph_store)
    flows = build_flows(components, graph_store.get_inferred_requests())
    print(f"Deduced {len(flows)} flow(s) from the traces the crawl walked.")
    graph_store.record_flows(flows, run_id=run_id)


@dataclass
class DocsRunResult:
    """`DocsEngine.run()`'s return value - the output documents from one
    docs-only pass. Details: docs/dev/core/docs_engine.md#docsrunresult
    """

    site: str
    documents: Tuple[ProducedDocument, ...] = ()
    manifest_path: str = ""
    index_path: str = ""
    # Phase C's own entry point (ADR-0016 point 4) - the file to open in
    # a browser, distinct from `index_path`'s cross-run Markdown index.
    # Details: docs/dev/core/docs_engine.md#docsrunresultdashboard_path
    dashboard_path: str = ""


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
        export_json: bool = False,
        documents: Optional[List[str]] = None,
    ) -> None:
        self.agent = agent
        self.graph_store = graph_store
        self.site = site
        self.out_dir = out_dir
        self.tree_ascii = tree_ascii
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
            export_json=config.export_json,
            documents=config.documents,
        )

    def run(self) -> DocsRunResult:
        """Project the navigation graph, derive the semantic tier, then
        generate every configured document from `site`'s existing graph
        store - no crawling. Works against a `static`-only DB: `pragma
        cluster`/`pragma dynamic` having run is a richer input, not a
        requirement - the semantic-tier passes below derive whatever the
        store already holds, empty or not.
        Details: docs/dev/core/docs_engine.md#run
        """
        finished_pages, total_pages = self.graph_store.count_visited()
        if total_pages == 0:
            print(
                f"Warning: {self.site} has no pages recorded in this graph store - "
                "did you run `pragma static` first, or point --graph-store at the right backend?"
            )
        unexplored_components, total_components = self.graph_store.count_unexplored_components()

        # CachingGraphStore from here on: every whole-site read below is
        # safe to memoize per method once nothing is still writing.
        # Details: docs/dev/core/docs_engine.md#run
        graph_store = CachingGraphStore(self.graph_store)
        print("Projecting the navigation graph into modules and metrics...")
        apply_graph_projection(graph_store, self.site)

        # Stamped onto every DERIVED_FROM edge the semantic-tier passes
        # below write, so a reader can tell which run concluded what - the
        # same role Engine._run_async's own run_id played before it was
        # inherited here (issue #242).
        run_id = _timestamp()
        print("Deducing the data model from the forms found...")
        _apply_data_model(graph_store, run_id)
        print("Deriving rules from the constraints forms declared...")
        _apply_rules(graph_store, run_id)
        print("Deriving screens from the pages the crawl finished...")
        _apply_screens(graph_store, self.agent, run_id)
        print("Deriving flows from the traces the crawl walked...")
        _apply_flows(graph_store, run_id)

        run_timestamp = _timestamp()
        request = DocumentRequest(
            graph_store=graph_store,
            site=self.site,
            agent=self.agent,
            settings={
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

        kpi_context = KpiContext(
            pages_finished=finished_pages, pages_total=total_pages,
            components_explored=total_components - unexplored_components, components_total=total_components,
        )
        dashboard_context = DashboardRunContext(kpi_context=kpi_context, site=self.site, out_dir=self.out_dir)
        dashboard_path = write_dashboard(produced, dashboard_context)

        self.graph_store.close()
        return DocsRunResult(
            site=self.site, documents=tuple(produced), manifest_path=manifest_path, index_path=index_path,
            dashboard_path=dashboard_path,
        )

    def _document_names(self) -> List[str]:
        """Which documents this run generates: the configured list, plus
        `"export"` when the standalone `export_json` flag is on and the
        list didn't already ask for it.
        Details: docs/dev/core/docs_engine.md#_document_names
        """
        names = list(self.documents)
        if self.export_json and "export" not in names:
            names.append("export")
        return names
