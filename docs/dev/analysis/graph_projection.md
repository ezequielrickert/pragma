# analysis/graph_projection.py

## module

Materializes `get_edges()` into `networkx` for the analyses no storage engine
here provides natively: module detection, centrality, click depth, cycles.

**Why a Python library and not the database.** This is not a shortcoming of the
current backend - it was true of every engine this project considered. Neo4j
needs the GDS plugin, which is not installed; Kùzu and DuckDB never had graph
algorithms at all. In all three the answer is a library over an edge list, so
the projection lives outside storage rather than being ported between backends.

**No `GraphStore` dependency.** Pure functions over plain data - edges in,
computed facts out - the same shape `generators/user_flows.py::build_flow_graph`
already uses. `Engine` supplies the edges and writes the results back; this
module has no storage opinion, which is why swapping the backend did not touch
it.

This is what turns "1,400 edges" into "6 modules, named, with depths". The
results are read back by `generators/architecture_map.py` (D13) and by
`GraphPRDSynthesizer`, which groups its sections by module instead of listing
pages flat.

### The two caps

`simple_cycles` enumerates every distinct cycle, and on a densely cross-linked
real site that is combinatorially large. `_MAX_CYCLE_LENGTH` and
`_MAX_CYCLES_REPORTED` are defensive backstops in the same "bounded, not
exhaustive" spirit the rest of this pipeline applies: a document saying "50+
navigation cycles found, showing the first 50" is useful, and a hung projection
pass is not.

## pagemetrics

One page's position in the navigation graph.

`click_depth` is `Optional` and that distinction carries weight: `None` means the
root cannot reach this page at all - a disconnected page, or no root supplied -
which is different from depth `0`. Every consumer has to keep them apart, and
`architecture_map` reports the `None` group separately for exactly that reason.

`is_articulation_point` is a cut vertex: removing this page disconnects the
(undirected) navigation graph, so the site has no alternate route around it.
That is the fact D13 reports as a bottleneck and the PRD states per page,
because it is a property of the whole graph that a model shown one page cannot
infer.

## pagemodule

One page's Louvain community, plus the label `_module_label` derives from the
members' shared URL path prefix.

The label is **deterministic and has no model call**, matching
`component_family.py`'s "clustering is pure" discipline. Narrating a better name
would be a separate, explicitly impure step - the same split
`component_family_narrator.py` draws. An empty label is a real outcome (a module
whose pages share no prefix), which is why consumers fall back to the module id
rather than rendering a blank.

## graphprojectionresult

`metrics`, `modules`, and `cycles`.

**`cycles` is computed every run and persisted nowhere.** There is no column and
no table for it, so `Engine` drops it after printing a count. That is a real gap
in D13's coverage rather than an oversight to fix quietly: storing them means a
new table, and the alternative - a document recomputing the whole projection to
get at them - would run betweenness twice per run to print one list. Recorded in
`docs/dev/database/ladybug/analysis.md` and in D13's own closing section.
