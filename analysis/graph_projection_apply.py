"""I/O wrapper around `project_graph`: reads a graph store's edges,
writes the computed page metrics/modules back.

Split from `graph_projection.py` for the same reason
`analysis/component_matching_pipeline.py` is split from
`analysis/leaf_feature_vector.py`/`composite_matching.py`: those modules
stay pure/no-I/O (their own docstrings are explicit about it), this one
is the impure caller -
shared by `Engine`'s fused pipeline and `pragma docs`
(`core/docs_engine.py`), which absorbed this as its own first internal
step since nothing but doc generation consumes projection output.
Details: docs/dev/analysis/graph_projection_apply.md#module
"""
from __future__ import annotations

from typing import Any

from .graph_projection import project_graph


def apply_graph_projection(graph_store: Any, root: str) -> None:
    """Post-hoc, whole-site pass: materialize the navigation graph into
    `networkx` and write back per-page metrics and module assignments.

    Args:
        graph_store: same store the crawl wrote to.
        root: the crawl's own start URL, `route_shape`d to match every
            other page key in the graph - `project_graph`'s `click_depth`
            is BFS distance from here. `pragma docs` passes its bare
            `site` argument instead of a URL, which is already the same
            string a root-page crawl's own `route_shape`d start URL would
            collapse to.

    Returns:
        None. `project_graph` (`analysis/graph_projection.py`) computes
        in/out degree, click depth, betweenness, PageRank, articulation
        points, and Louvain module assignment; results are written via
        `record_page_metrics`/`record_page_modules` - full rebuilds, same
        contract as `record_component_families`.
    Details: docs/dev/analysis/graph_projection_apply.md#apply_graph_projection
    """
    result = project_graph(graph_store.get_edges(), root=root)
    graph_store.record_page_metrics([m.as_dict() for m in result.metrics])
    graph_store.record_page_modules([m.as_dict() for m in result.modules])
    if result.cycles:
        print(f"Graph projection: {len(result.cycles)} navigation cycle(s) found.")
