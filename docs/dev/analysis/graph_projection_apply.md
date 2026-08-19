# analysis/graph_projection_apply.py

## module

I/O wrapper around `project_graph` (`analysis/graph_projection.py`, which
stays pure/no-I/O on purpose - see that module's own docstring). Split
out for the same reason `analysis/component_clustering.py` is split from
`generators/component_family.py`: this is the impure caller, shared by
`Engine`'s fused pipeline and `pragma docs` (`core/docs_engine.py`),
which absorbed this as its own first internal step since nothing but
doc generation consumes projection output.

## apply_graph_projection

Materializes the navigation graph into `networkx` and writes per-page
metrics and module assignments back onto each `Page` via
`record_page_metrics`/`record_page_modules` - full rebuilds, same
contract as `record_component_families`. Independent of every other
whole-site pass - it reads only `get_edges`, not the component ledger -
so it can run in any order relative to them.

`root` is the crawl's own start URL, `route_shape`d to match every other
page key in the graph (`project_graph`'s `click_depth` is BFS distance
from here) - `Engine` passes `route_shape(url)`; `pragma docs` passes
its bare `site` argument instead, which is already the same string a
root-page crawl's own `route_shape`d start URL collapses to.

What this produces was unreadable by any document until
`get_page_metrics` existed; see `docs/dev/database/ladybug/analysis.md`.
