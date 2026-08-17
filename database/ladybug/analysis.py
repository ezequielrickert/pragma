"""Derived-graph-metrics write path for `LadybugGraphStore` -
`Engine`'s post-crawl `_apply_graph_projection` pass writes
`analysis/graph_projection.py::project_graph`'s output here. Split out
for the same file-size reason the retired DuckDB backend split
`_duckdb_analysis_store.py` out on its own.
`_LadybugAnalysisMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)` existing
on whatever it ends up mixed into.

Unlike the retired DuckDB backend's `page_metrics`/`page_modules` child
tables, these are `Page` properties in the new schema (the design rule:
node when traversed/joined, property when always read whole with its
parent - a page's own centrality/module is exactly the latter). Both
methods are `SET`s against existing `Page` nodes, not inserts into a
separate table.

`get_page_metrics`/`get_page_modules` are not ported: both had zero
production callers in the retired backend (only their own writers,
`Engine`'s post-crawl pass, ever touched this data again - no generator
reads it back through these methods).

Details: docs/dev/database/ladybug/analysis.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List


class _LadybugAnalysisMixin:
    """Details: docs/dev/database/ladybug/analysis.md#_ladybuganalysismixin"""

    def record_page_metrics(self, metrics: List[Dict[str, Any]]) -> None:
        """Write `project_graph`'s per-page metrics onto each `Page` node.
        Not a full-table rebuild the way the retired DuckDB backend's
        `DELETE`-then-`INSERT` was - there is no separate table to clear,
        only properties to overwrite on nodes that already exist.
        Details: docs/dev/database/ladybug/analysis.md#record_page_metrics
        """
        if not metrics:
            return
        rows = [
            {
                "url": m["url"], "in_degree": m.get("in_degree", 0),
                "out_degree": m.get("out_degree", 0), "click_depth": m.get("click_depth"),
                "betweenness": m.get("betweenness", 0.0), "pagerank": m.get("pagerank", 0.0),
                "is_articulation_point": bool(m.get("is_articulation_point", False)),
            }
            for m in metrics
        ]

        def op(conn) -> None:
            # click_depth/betweenness/pagerank all explicitly CAST: an
            # UNWIND batch whose numeric column is None on every row (a
            # disconnected site's click_depth; a genuinely all-zero
            # betweenness pass) makes Ladybug infer that column as STRING
            # rather than the real type and reject the write - confirmed
            # against the real engine, and not specific to DOUBLE columns,
            # see database/ladybug/_cypher.py's own comment for the first
            # instance of this found (in the component/text-content
            # writers, which share a helper this module's clause is too
            # short to bother pulling in).
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (p:Page {url: r.url})
                SET p.in_degree = r.in_degree, p.out_degree = r.out_degree,
                    p.click_depth = CAST(r.click_depth AS INT64),
                    p.betweenness = CAST(r.betweenness AS DOUBLE),
                    p.pagerank = CAST(r.pagerank AS DOUBLE),
                    p.is_articulation_point = r.is_articulation_point
                """,
                {"rows": rows},
            )

        self._call(op)

    def record_page_modules(self, modules: List[Dict[str, Any]]) -> None:
        """Write `project_graph`'s Louvain module assignment onto each
        `Page` node.
        Details: docs/dev/database/ladybug/analysis.md#record_page_modules
        """
        if not modules:
            return
        rows = [
            {"url": m["url"], "module_id": m["module_id"], "module_label": m.get("module_label", "")}
            for m in modules
        ]

        def op(conn) -> None:
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (p:Page {url: r.url})
                SET p.module_id = r.module_id, p.module_label = r.module_label
                """,
                {"rows": rows},
            )

        self._call(op)
