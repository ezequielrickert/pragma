"""Derived-graph-metrics CRUD for `DuckDBGraphStore` - Storage Phase 7's
`page_metrics`/`page_modules`, split out for the same file-size reason as
every other mixin here. `_DuckDBAnalysisMixin` is combined into the public
`DuckDBGraphStore` class via multiple inheritance; every method here
relies on `self._call(...)` existing on whatever it ends up mixed into.

Details: docs/dev/database/_duckdb_analysis_store.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List


class _DuckDBAnalysisMixin:
    """Details: docs/dev/database/_duckdb_analysis_store.md#_duckdbanalysismixin"""

    def record_page_metrics(self, site: str, metrics: List[Dict[str, Any]]) -> None:
        rows = [
            {
                "site": site, "url": m["url"], "in_degree": m.get("in_degree", 0),
                "out_degree": m.get("out_degree", 0), "click_depth": m.get("click_depth"),
                "betweenness": m.get("betweenness", 0.0), "pagerank": m.get("pagerank", 0.0),
                "is_articulation_point": bool(m.get("is_articulation_point", False)),
            }
            for m in metrics
        ]

        def op(conn) -> None:
            # Full rebuild, not an incremental merge - a page's centrality/
            # depth genuinely can shift as the crawl discovers more pages.
            conn.execute("DELETE FROM page_metrics WHERE site = $site", {"site": site})
            if rows:
                conn.executemany(
                    """
                    INSERT INTO page_metrics (site, url, in_degree, out_degree, click_depth,
                                               betweenness, pagerank, is_articulation_point)
                    VALUES ($site, $url, $in_degree, $out_degree, $click_depth,
                            $betweenness, $pagerank, $is_articulation_point)
                    """,
                    rows,
                )

        self._call(op)

    def get_page_metrics(self, site: str) -> Dict[str, Dict[str, Any]]:
        def op(conn) -> Dict[str, Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT url, in_degree, out_degree, click_depth, betweenness, pagerank, is_articulation_point
                FROM page_metrics WHERE site = $site
                """,
                {"site": site},
            ).fetchall()
            return {
                url: {
                    "in_degree": in_degree, "out_degree": out_degree, "click_depth": click_depth,
                    "betweenness": betweenness, "pagerank": pagerank,
                    "is_articulation_point": is_articulation_point,
                }
                for url, in_degree, out_degree, click_depth, betweenness, pagerank, is_articulation_point in rows
            }

        return self._call(op)

    def record_page_modules(self, site: str, modules: List[Dict[str, Any]]) -> None:
        rows = [
            {"site": site, "url": m["url"], "module_id": m["module_id"], "module_label": m.get("module_label", "")}
            for m in modules
        ]

        def op(conn) -> None:
            conn.execute("DELETE FROM page_modules WHERE site = $site", {"site": site})
            if rows:
                conn.executemany(
                    "INSERT INTO page_modules (site, url, module_id, module_label) "
                    "VALUES ($site, $url, $module_id, $module_label)",
                    rows,
                )

        self._call(op)

    def get_page_modules(self, site: str) -> Dict[str, Dict[str, Any]]:
        def op(conn) -> Dict[str, Dict[str, Any]]:
            rows = conn.execute(
                "SELECT url, module_id, module_label FROM page_modules WHERE site = $site",
                {"site": site},
            ).fetchall()
            return {url: {"module_id": module_id, "module_label": module_label} for url, module_id, module_label in rows}

        return self._call(op)
