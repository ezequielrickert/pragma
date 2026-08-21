"""Module boundaries, depth, and bottleneck derivation over the export
graph vocabulary - docs/adr/0007, the source of these facts for both
`export.json`'s reserved `Modulo` nodes (ADR-0002) and
`architecture.calm.json` (docs/adr/0010).

Takes the same `@graph` node list `generators/graph_export.py::build_export_graph`
assembles (`Pantalla`/`Componente`/`Endpoint` nodes, `contiene`/`navega_a`/
`dispara`/`consume` edges) as its only input - the same call `export.json`
itself made, not a second, independently-detected structure (ADR-0010
point 4). Lives in `core/` rather than `generators/`: the caller
(`generators/graph_export.py`, `generators/architecture_calm.py`) wires
this together with `build_export_graph`, and `core/` never imports from
`generators/`.

`build_screen_graph` is the one exception to "takes the full export graph
as input": a minimal `Pantalla`-only builder for callers (`prd.md`'s module
grouping, `gherkin`'s `@MOD-<x>` tags) that need module derivation but
can't import `graph_export.py` without a circular import - see its own
docstring.

Details: docs/dev/core/graph_metrics.md#module
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx

from utils.short_hash import short_hash

_EDGE_PREDICATES = ("contiene", "navega_a", "dispara", "consume")

# ADR-0007 point 3: the top 90th percentile of betweenness, combined with
# an in-degree floor - a node passing only one of the two isn't a single
# point of passage on its own, just a busy one or a well-linked one.
_BOTTLENECK_BETWEENNESS_PERCENTILE = 90
_BOTTLENECK_MIN_IN_DEGREE = 3

# Two pages sharing a first path segment is the minimum evidence for a
# real path-prefix cluster (ADR-0007's "high-confidence" grouping) - one
# page that merely has a path is not a cluster, and gets a chance at
# Leiden instead rather than a module of one.
_MIN_PATH_PREFIX_CLUSTER_SIZE = 2


def _slug(segment: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-") or "module"


def build_screen_graph(store: Any, edges: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A minimal `Pantalla`-only `@graph`-shaped list - just enough for
    `compute_graph_metrics`'s own module derivation, for any caller that
    needs module boundaries without building the full export graph.

    Shared by `generators/requirements.py` (`prd.md`'s module grouping,
    ADR-0009) and `generators/gherkin.py` (`@MOD-<slug|hash>` tags,
    ADR-0013) - both need exactly this shape and neither can import
    `generators/graph_export.py::build_export_graph` directly without a
    circular import (`graph_export.py` itself imports both of them for
    `export.json`'s `Requisito`/traceability population). Living here
    rather than in either generator avoids tripling this same small
    function across a third module.
    Details: docs/dev/core/graph_metrics.md#build_screen_graph
    """
    nodes: Dict[str, Dict[str, Any]] = {
        row["url"]: {"id": row["url"], "type": "Pantalla"}
        for row in store.get_progress_table_rows()
        if row.get("status") != "External"
    }
    for edge in edges:
        source, destination = edge["from"], edge["to"]
        if source not in nodes or destination not in nodes:
            continue
        targets = nodes[source].setdefault("navega_a", [])
        if destination not in targets:
            targets.append(destination)
    return list(nodes.values())


@dataclass(frozen=True)
class NodeMetrics:
    """One node's position in the unified screen/component/endpoint graph.
    Details: docs/dev/core/graph_metrics.md#nodemetrics
    """

    node_id: str
    node_type: str
    in_degree: int
    # BFS hops from the crawl's entry screen; None if unreachable from it
    # or no root was supplied.
    depth: Optional[int]
    betweenness: float
    is_bottleneck: bool


@dataclass(frozen=True)
class NodeModule:
    """One screen's derived module assignment.
    Details: docs/dev/core/graph_metrics.md#nodemodule
    """

    node_id: str
    module_id: str
    module_label: str


@dataclass(frozen=True)
class GraphMetrics:
    """Everything one `compute_graph_metrics` call derived.
    Details: docs/dev/core/graph_metrics.md#graphmetrics
    """

    node_metrics: Tuple[NodeMetrics, ...]
    node_modules: Tuple[NodeModule, ...]


def _build_digraph(graph_nodes: Sequence[Dict[str, Any]]) -> "nx.DiGraph":
    graph = nx.DiGraph()
    for node in graph_nodes:
        graph.add_node(node["id"], type=node.get("type", ""))
        for predicate in _EDGE_PREDICATES:
            for target in node.get(predicate, []):
                graph.add_edge(node["id"], target)
    return graph


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile - no numpy/scipy dependency for one
    threshold computation.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * percentile / 100))
    return ordered[index]


def _node_metrics(graph: "nx.DiGraph", root: Optional[str]) -> Tuple[NodeMetrics, ...]:
    if graph.number_of_nodes() == 0:
        return ()
    betweenness = nx.betweenness_centrality(graph)
    depths = dict(nx.single_source_shortest_path_length(graph, root)) if root and root in graph else {}
    threshold = _percentile(list(betweenness.values()), _BOTTLENECK_BETWEENNESS_PERCENTILE)

    metrics = []
    for node_id, data in graph.nodes(data=True):
        in_degree = graph.in_degree(node_id)
        score = betweenness.get(node_id, 0.0)
        metrics.append(
            NodeMetrics(
                node_id=node_id, node_type=data.get("type", ""), in_degree=in_degree,
                depth=depths.get(node_id), betweenness=score,
                # score > 0 as well as >= threshold: a graph with mostly-zero
                # betweenness can have a zero-valued 90th percentile, which
                # would otherwise call every in_degree>=3 node a bottleneck
                # regardless of whether it actually sits on any real path.
                is_bottleneck=score > 0 and score >= threshold and in_degree >= _BOTTLENECK_MIN_IN_DEGREE,
            )
        )
    return tuple(sorted(metrics, key=lambda m: m.node_id))


def _first_path_segment(pantalla_id: str) -> Optional[str]:
    """`"example.com/admin/users"` -> `"admin"` - `None` for a root page
    (no segments) or a `Pantalla` id with nothing after the host.
    """
    _, _, path = pantalla_id.partition("/")
    segments = [segment for segment in path.split("/") if segment]
    return segments[0] if segments else None


def _path_prefix_modules(pantalla_ids: Sequence[str]) -> Dict[str, str]:
    """`{node_id: prefix_segment}` for every screen whose first path
    segment is shared by at least `_MIN_PATH_PREFIX_CLUSTER_SIZE` other
    screens - ADR-0007's high-confidence first stage.
    """
    by_segment: Dict[str, List[str]] = {}
    for node_id in pantalla_ids:
        segment = _first_path_segment(node_id)
        if segment:
            by_segment.setdefault(segment, []).append(node_id)
    return {
        node_id: segment
        for segment, members in by_segment.items()
        if len(members) >= _MIN_PATH_PREFIX_CLUSTER_SIZE
        for node_id in members
    }


def _leiden_modules(graph: "nx.DiGraph", remaining: Set[str]) -> List[List[str]]:
    """Leiden community detection over just the screens
    `_path_prefix_modules` left unclustered - ADR-0007's second stage.
    Their connections to already-clustered screens carry no information
    about how the *remainder* should be grouped, so only their own
    induced subgraph is considered.

    Uses `python-igraph`/`leidenalg` directly rather than networkx's own
    `leiden_communities` dispatcher: confirmed live that networkx 3.6.1
    ships it as a backend-only stub with no default implementation
    (`NotImplementedError` on a bare call) - `igraph`/`leidenalg` are the
    real, actively-maintained implementation the networkx docs point to.
    Details: docs/dev/core/graph_metrics.md#_leiden_modules
    """
    subgraph = graph.subgraph(remaining).to_undirected()
    if subgraph.number_of_edges() == 0:
        return [[node_id] for node_id in sorted(remaining)]

    import igraph as ig
    import leidenalg

    members = sorted(subgraph.nodes)
    index_by_id = {node_id: position for position, node_id in enumerate(members)}
    handle = ig.Graph()
    handle.add_vertices(len(members))
    handle.add_edges([(index_by_id[a], index_by_id[b]) for a, b in subgraph.edges])
    partition = leidenalg.find_partition(handle, leidenalg.ModularityVertexPartition, seed=42)
    return [sorted(members[i] for i in community) for community in partition]


def _node_modules(graph: "nx.DiGraph") -> Tuple[NodeModule, ...]:
    """Every screen's module assignment - `MOD-<slug>` for a path-prefix
    cluster (readable, e.g. `MOD-admin`), `MOD-<hash>` for a Leiden
    community with no dominant prefix - the literal id format ADR-0013
    locked, reused here rather than invented fresh.
    Details: docs/dev/core/graph_metrics.md#_node_modules
    """
    pantalla_ids = [node_id for node_id, data in graph.nodes(data=True) if data.get("type") == "Pantalla"]
    prefix_assignment = _path_prefix_modules(pantalla_ids)

    modules = [
        NodeModule(node_id=node_id, module_id=f"MOD-{_slug(segment)}", module_label=segment.replace("-", " ").title())
        for node_id, segment in prefix_assignment.items()
    ]

    remaining = set(pantalla_ids) - set(prefix_assignment)
    if remaining:
        for members in _leiden_modules(graph, remaining):
            module_id = f"MOD-{short_hash(','.join(members))}"
            modules += [NodeModule(node_id=node_id, module_id=module_id, module_label="") for node_id in members]

    return tuple(sorted(modules, key=lambda m: (m.module_id, m.node_id)))


def compute_graph_metrics(graph_nodes: Sequence[Dict[str, Any]], root: Optional[str] = None) -> GraphMetrics:
    """Derive module boundaries, depth, and bottleneck classification over
    `graph_nodes` (`export.json`'s own `@graph` shape - a list of
    `{"id", "type", ...edge-predicate arrays}` dicts).

    Args:
        graph_nodes: `Pantalla`/`Componente`/`Endpoint` nodes, as
            `generators/graph_export.py::build_export_graph` assembles
            them before adding `Modulo`/`Token`.
        root: the crawl's entry screen id (a `Pantalla` id, already
            route-shaped), for BFS depth. `None` leaves every node's
            `depth` as `None`.
    Details: docs/dev/core/graph_metrics.md#compute_graph_metrics
    """
    graph = _build_digraph(graph_nodes)
    return GraphMetrics(node_metrics=_node_metrics(graph, root), node_modules=_node_modules(graph))
