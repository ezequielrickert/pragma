"""Derived graph-analysis half of the `GraphStore` contract - Storage
Phase 7's `page_metrics`/`page_modules`, computed by
`analysis/graph_projection.py` from `get_edges` and written back so a
generator reads them as ordinary tables, the same way it reads any other
ledger. Split into its own file for the same reason every other
`GraphStore` concern is split (see `_component_store_interface.py`'s
module docstring) - added after that split landed, so it starts out
already in the right shape rather than growing `interfaces.py` again.

Must itself subclass `ABC`, not a plain class - see
`_component_store_interface.py`'s module docstring for why (a plain
mixin's `@abstractmethod`s are silently unenforced once composed). Has no
abstract methods of its own today, same as `_containment_interface.py`,
but keeps the `ABC` base for the same forward-consistency reason.

`_AnalysisInterface` is combined into the public `GraphStore` class in
`interfaces.py` via multiple inheritance; it is never instantiated on its
own.

Details: docs/dev/core/_analysis_interface.md#module
"""
from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List


class _AnalysisInterface(ABC):
    """Details: docs/dev/core/_analysis_interface.md#_analysisinterface"""

    def record_page_metrics(self, site: str, metrics: List[Dict[str, Any]]) -> None:
        """Replace `site`'s whole `page_metrics` table with `metrics`.

        Args:
            site: which site's metrics to replace.
            metrics: `[{"url", "in_degree", "out_degree", "click_depth",
                "betweenness", "pagerank", "is_articulation_point"}, ...]` -
                `analysis.graph_projection.project_graph`'s own per-page
                output shape. `click_depth` is `None` for a page the
                projection's root can't reach.

        Returns:
            None - a write-only side effect. Full rebuild, not an
            incremental merge, same "cluster membership isn't guaranteed
            stable across runs" reasoning as `record_component_families` -
            a page's centrality/depth genuinely can shift as the crawl
            discovers more of the site.

        Not abstract - a backend with no use for derived graph metrics can
        ignore this, same reasoning as `record_accessibility_violations`.
        Details: docs/dev/core/interfaces.md#record_page_metrics
        """

    def get_page_metrics(self, site: str) -> Dict[str, Dict[str, Any]]:
        """`{url: {"in_degree", "out_degree", "click_depth", "betweenness",
        "pagerank", "is_articulation_point"}}` for `site`. `{}` if
        `record_page_metrics` was never called.
        Details: docs/dev/core/interfaces.md#get_page_metrics
        """
        return {}

    def record_page_modules(self, site: str, modules: List[Dict[str, Any]]) -> None:
        """Replace `site`'s whole `page_modules` table with `modules`.

        Args:
            site: which site's modules to replace.
            modules: `[{"url", "module_id", "module_label"}, ...]` -
                `analysis.graph_projection.project_graph`'s own per-page
                module-assignment output, one entry per page that belongs
                to a detected module.

        Returns:
            None - a write-only side effect. Full rebuild, same reasoning
            as `record_page_metrics`.
        Details: docs/dev/core/interfaces.md#record_page_modules
        """

    def get_page_modules(self, site: str) -> Dict[str, Dict[str, Any]]:
        """`{url: {"module_id", "module_label"}}` for `site`. `{}` if
        `record_page_modules` was never called.
        Details: docs/dev/core/interfaces.md#get_page_modules
        """
        return {}
