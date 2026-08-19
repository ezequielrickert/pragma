"""Materializes `GraphStore.get_edges` into `networkx` for the analyses no
database engine here provides natively - module detection, centrality,
click depth, cycle/bottleneck detection - and produces `page_metrics`/
`page_modules` rows a generator can read like any other table.

This is what turns "1,400 edges" into "6 modules, named, with depths":
module detection is unavailable in every storage engine this project
considered (Neo4j needs the GDS plugin, not installed; Kùzu/DuckDB never
had graph algorithms) - in every one of them it's a Python library over
an edge list. Deliberately no `GraphStore` dependency here: pure functions
over plain data, the same "GraphStore.get_edges output in, computed facts
out" shape `generators/user_flows.py::build_flow_graph` already uses -
`Engine`/a generator supplies the edges and writes results back, this
module has no storage opinion of its own.

Details: docs/dev/analysis/graph_projection.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import networkx as nx

# simple_cycles enumerates every distinct cycle - on a densely
# cross-linked real site that can be combinatorially large. Both caps are
# defensive backstops, the same "bounded, not exhaustive" discipline
# probe_focus.js's _MAX_TAB_STEPS and axe_run.js's per-rule node cap
# already apply elsewhere in this pipeline - a document that says "50+
# navigation cycles found, showing the first 50" is useful; a hung
# projection pass is not.
_MAX_CYCLE_LENGTH = 8
_MAX_CYCLES_REPORTED = 50


@dataclass(frozen=True)
class PageMetrics:
    """One page's position in the navigation graph.
    Details: docs/dev/analysis/graph_projection.md#pagemetrics
    """

    url: str
    in_degree: int
    out_degree: int
    # None if `root` can't reach this page at all (a disconnected page, or
    # no root was supplied).
    click_depth: Optional[int]
    betweenness: float
    pagerank: float
    # A cut vertex: removing this page disconnects the (undirected)
    # navigation graph - the site has no alternate route around it.
    is_articulation_point: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "in_degree": self.in_degree, "out_degree": self.out_degree,
            "click_depth": self.click_depth, "betweenness": self.betweenness,
            "pagerank": self.pagerank, "is_articulation_point": self.is_articulation_point,
        }


@dataclass(frozen=True)
class PageModule:
    """One page's assigned module (Louvain community).
    Details: docs/dev/analysis/graph_projection.md#pagemodule
    """

    url: str
    module_id: int
    module_label: str

    def as_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "module_id": self.module_id, "module_label": self.module_label}


@dataclass(frozen=True)
class GraphProjectionResult:
    """Everything one `project_graph` call computed.
    Details: docs/dev/analysis/graph_projection.md#graphprojectionresult
    """

    metrics: Tuple[PageMetrics, ...]
    modules: Tuple[PageModule, ...]
    # Each cycle as an ordered tuple of urls (A -> B -> C -> back to A) -
    # capped at _MAX_CYCLES_REPORTED, longest _MAX_CYCLE_LENGTH each.
    cycles: Tuple[Tuple[str, ...], ...]


def module_display_name(module_id: Optional[int], module_label: str) -> str:
    """What to call a module in a document - its label, or its id when the
    prefix heuristic produced nothing.

    An empty `module_label` is a real outcome of `_module_label` (a module
    whose pages share no URL prefix), not a failure, so the fallback is part
    of the naming rule rather than each reader's own guess. Public and living
    here because this module owns what a module label is; two generators
    derived the same fallback independently before this existed, which is one
    edit away from a document that names the same module two ways.
    Details: docs/dev/analysis/graph_projection.md#module_display_name
    """
    return module_label or f"Module {module_id}"


def _module_label(urls: Sequence[str]) -> str:
    """A human-readable label for a module, derived from its members'
    shared URL path prefix - deterministic, no LLM. Matches
    `component_family.py`'s "clustering is pure/no-LLM" discipline;
    narrating a *better* label is a separate, explicitly-impure step if
    ever wanted, the same split `component_family_narrator.py` already
    draws for component families.
    """
    segments_per_url = []
    for url in urls:
        path = urlsplit(url if "//" in url else f"//{url}").path
        segments_per_url.append([s for s in path.split("/") if s])
    if not segments_per_url:
        return "Module"

    shortest = min(len(segments) for segments in segments_per_url)
    common: List[str] = []
    for i in range(shortest):
        values = {segments[i] for segments in segments_per_url}
        if len(values) != 1:
            break
        common.append(values.pop())

    if not common:
        return "Module"
    return " / ".join(seg.replace("-", " ").replace("_", " ").title() for seg in common)


def _click_depths(graph: "nx.DiGraph", root: Optional[str]) -> Dict[str, Optional[int]]:
    if not root or root not in graph:
        return {}
    return dict(nx.single_source_shortest_path_length(graph, root))


def _cycles(graph: "nx.DiGraph") -> Tuple[Tuple[str, ...], ...]:
    found = []
    for cycle in nx.simple_cycles(graph, length_bound=_MAX_CYCLE_LENGTH):
        found.append(tuple(cycle))
        if len(found) >= _MAX_CYCLES_REPORTED:
            break
    return tuple(found)


def project_graph(edges: List[Dict[str, Any]], root: Optional[str] = None) -> GraphProjectionResult:
    """Compute every derived graph fact `page_metrics`/`page_modules` need.

    Args:
        edges: `GraphStore.get_edges` output - each `{"from", "to", ...}`.
            Only `from`/`to` are read; `component`/`action`/observation
            fields are this function's business.
        root: the crawl's own start URL (already `route_shape`d, matching
            every other page key), for `click_depth`. `None` leaves every
            page's `click_depth` as `None` - a valid, if less useful,
            result rather than an error.

    Returns:
        A `GraphProjectionResult`. `()` for every field on an edge-less
        input - an unreachable/never-crawled site produces nothing to
        project, not an error.
    """
    graph = nx.DiGraph()
    for edge in edges:
        graph.add_edge(edge["from"], edge["to"])

    if graph.number_of_nodes() == 0:
        return GraphProjectionResult(metrics=(), modules=(), cycles=())

    undirected = graph.to_undirected()
    depths = _click_depths(graph, root)
    betweenness = nx.betweenness_centrality(graph)
    pagerank = nx.pagerank(graph)
    cut_vertices = set(nx.articulation_points(undirected)) if undirected.number_of_edges() else set()

    metrics = tuple(
        PageMetrics(
            url=node,
            in_degree=graph.in_degree(node),
            out_degree=graph.out_degree(node),
            click_depth=depths.get(node),
            betweenness=betweenness.get(node, 0.0),
            pagerank=pagerank.get(node, 0.0),
            is_articulation_point=node in cut_vertices,
        )
        for node in sorted(graph.nodes)
    )

    if undirected.number_of_edges():
        communities = nx.algorithms.community.louvain_communities(undirected, seed=42)
    else:
        # Every node its own module - Louvain needs at least one edge to
        # say anything about grouping.
        communities = [{node} for node in graph.nodes]

    modules = tuple(
        sorted(
            (
                PageModule(url=url, module_id=module_id, module_label=_module_label(sorted(community)))
                for module_id, community in enumerate(communities)
                for url in community
            ),
            key=lambda m: (m.module_id, m.url),
        )
    )

    return GraphProjectionResult(metrics=metrics, modules=modules, cycles=_cycles(graph))
