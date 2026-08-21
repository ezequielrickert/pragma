"""The `pragma cluster` entry point: component-family clustering as its
own standalone pass over a site's existing graph store.

`pragma static` writes the components; `pragma cluster` reads them back,
groups them into `ComponentFamily` patterns, and writes those back -
nothing here re-crawls or re-navigates anything. `pragma dynamic`'s own
ticket is what makes use of the result (skipping redundant interaction on
components a family already covers).
Details: docs/dev/core/cluster_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from analysis.component_matching_pipeline import apply_component_matching
from .config import PragmaConfig
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


@dataclass
class ClusterRunResult:
    """`ClusterEngine.run()`'s return value - a summary of what the graph
    store now holds, not a document (cluster generates none).
    Details: docs/dev/core/cluster_engine.md#clusterrunresult
    """

    site: str
    families: int


class ClusterEngine:
    """Wires an agent and a graph store, then clusters one site's already-
    discovered components. Details: docs/dev/core/cluster_engine.md#clusterengine
    """

    def __init__(self, agent: Any, graph_store: Any, site: str) -> None:
        self.agent = agent
        self.graph_store = graph_store
        self.site = site

    @classmethod
    def from_config(cls, config: PragmaConfig, site: str) -> "ClusterEngine":
        """Resolve the agent and graph store named in `config`, scoped to
        `site` - a bare host/slug, not a URL, since clustering resumes
        against a site a previous `pragma static` run already wrote
        rather than starting one of its own.
        Details: docs/dev/core/cluster_engine.md#from_config
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

        return cls(agent, graph_store, site)

    def run(self) -> ClusterRunResult:
        """Cluster `site`'s current component ledger and stop - see
        `analysis/component_matching_pipeline.py::apply_component_matching`
        for the actual four-step algorithm (leaf exact collapse, leaf
        family grouping, composite exact collapse, composite family
        grouping). Details: docs/dev/core/cluster_engine.md#run
        """
        _, total_components = self.graph_store.count_unexplored_components()
        if total_components == 0:
            print(
                f"Warning: {self.site} has no components recorded in this graph store - "
                "did you run `pragma static` first, or point --graph-store at the right backend?"
            )

        apply_component_matching(self.graph_store, self.agent)
        families = len(self.graph_store.get_component_families())
        self.graph_store.close()
        return ClusterRunResult(site=self.site, families=families)
