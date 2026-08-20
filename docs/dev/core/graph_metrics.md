# `core/graph_metrics.py`

## module

Module boundaries, depth, and bottleneck derivation over the export
graph vocabulary - docs/adr/0007, the source of these facts for both
`export.json`'s reserved `Modulo` nodes (ADR-0002) and
`architecture.calm.json` (docs/adr/0010).

Takes the same `@graph` node list `generators/graph_export.py::build_export_graph`
assembles as its only input - the same call `export.json` itself made,
not a second, independently-detected structure (ADR-0010 point 4). Lives
in `core/` rather than `generators/`: the caller
(`generators/graph_export.py`, `generators/architecture_calm.py`) wires
this together with `build_export_graph`, and `core/` never imports from
`generators/`.

## NodeMetrics

One node's position in the unified screen/component/endpoint graph -
`depth`, `betweenness`, and the derived `is_bottleneck` flag. Computed
for every node type in the graph, not just screens: ADR-0007 point 3
names "screens or API endpoints" as candidate bottlenecks.

## NodeModule

One screen's derived module assignment. Screen-scoped only - a
`Componente`/`Endpoint` node never gets a `module_id` of its own;
ADR-0007's own framing (`SCR-root`, screen depth) is about screens.

## GraphMetrics

Everything one `compute_graph_metrics` call derived - `node_metrics` and
`node_modules`, both keyed by node id, kept as two separate tuples rather
than merged: a `Componente`/`Endpoint` has metrics but no module, so a
single joined record would carry a field that's meaningless for most of
the nodes it describes.

## _percentile

Nearest-rank percentile over a plain list, no numpy/scipy dependency -
one threshold computation doesn't justify a new one.

## _node_metrics

Betweenness centrality and BFS depth from `root`, then the bottleneck
classification: `betweenness > 0` *and* `>= ` the 90th-percentile
threshold *and* `in_degree >= 3` (ADR-0007 point 3). The `> 0` guard is
the one addition beyond the ADR's literal wording: a graph with mostly-
zero betweenness (a small or sparsely-linked crawl) can have a
zero-valued 90th percentile too, which would otherwise call every
well-linked node a bottleneck regardless of whether it sits on any real
path between others.

## _first_path_segment

`"example.com/admin/users"` -> `"admin"` - the raw material
`_path_prefix_modules` clusters on.

## _path_prefix_modules

ADR-0007's high-confidence first stage: every screen whose first path
segment is shared by at least `_MIN_PATH_PREFIX_CLUSTER_SIZE` (2) other
screens. One page that merely has a path segment of its own isn't
evidence of a real cluster - it falls through to Leiden instead of
becoming a module of one, the same "not a real cluster on its own"
reasoning `tokens.json`'s system-candidate threshold applies to a
one-off style (docs/adr/0005).

## _leiden_modules

Leiden community detection over just the screens `_path_prefix_modules`
left unclustered (ADR-0007's second stage) - their connections to
already-clustered screens carry no information about how the *remainder*
should be grouped, so only their own induced subgraph is considered.

Uses `python-igraph`/`leidenalg` directly rather than networkx's own
`leiden_communities` dispatcher: confirmed live that networkx 3.6.1 ships
it as a backend-only stub with no default implementation
(`NotImplementedError` on a bare call, "This function does not have a
default NetworkX implementation... may only be run with an installable
backend"). `igraph`/`leidenalg` are the real, actively-maintained
implementation, installable from prebuilt wheels on this platform (no C
compiler needed, unlike the PyYAML source-build gap this sandbox already
had) - added as new pinned dependencies for exactly this reason.

## _node_modules

Combines both stages into one `NodeModule` tuple. `MOD-<slug>` for a
path-prefix cluster (readable, e.g. `MOD-admin`), `MOD-<hash>` for a
Leiden community with no dominant prefix - the literal id format
ADR-0013 locked (for `gherkin`'s own `@MOD-<slug|hash>` tag), reused here
rather than invented fresh; this module is the first to actually mint
one.

## compute_graph_metrics

The one entry point: `graph_nodes` (an `@graph`-shaped node list) plus an
optional `root` (a `Pantalla` id, already route-shaped) in, a
`GraphMetrics` out. An empty `graph_nodes` produces empty results rather
than an error - an unreachable or never-crawled site is a real, if
useless, input.
