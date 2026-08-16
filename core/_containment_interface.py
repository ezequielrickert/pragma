"""Structural-containment half of the `GraphStore` contract - split out of
`interfaces.py` for the same file-size reason as
`_component_store_interface.py`. `_ContainmentInterface` is combined into
the public `GraphStore` class in `interfaces.py` via multiple inheritance;
it is never instantiated on its own.

Has no `@abstractmethod`s of its own today (both methods below are
optional, same reasoning as `record_accessibility_violations`), but still
subclasses `ABC` for consistency with every sibling interface file here -
see `_component_store_interface.py`'s module docstring for why that
matters the moment this file ever does gain one.

Details: docs/dev/core/_containment_interface.md#module
"""
from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List


class _ContainmentInterface(ABC):
    """Which real layout/landmark containers (nav, section, aside, ...) a
    component sits inside - captured by `discover_components.js`'s
    `structuralAncestorsOf` (Storage Phase 5) so a post-hoc pass can group
    components into modules instead of only ever seeing a flat component
    list with no hierarchy at all. Not abstract - a backend with no
    structural-analysis use for this can ignore it, same reasoning as
    `record_accessibility_violations`. Both shipped graph backends (Neo4j,
    DuckDB) and the in-memory reference do implement it.
    Details: docs/dev/core/_containment_interface.md#_containmentinterface
    """

    def record_component_ancestors(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Replace a whole page's worth of components' structural ancestors
        in one call - batched the same way `record_components` batches a
        discovery pass's descriptive writes, since ancestor data exists for
        essentially every component (unlike `options`, which is rare).

        Args:
            site: which site this page belongs to.
            page_url: the page these components were discovered on.
            entries: `[{"path": <component path>, "ancestors": [{"path",
                "tag", "role", "landmark", "id", "class", "depth"}, ...]},
                ...]` - `path` is the component's own key, `ancestors` is
                exactly `discover_components.js`'s per-component
                `ancestors` field: one entry per structural container the
                component sits inside, nearest first (`depth` 1 = immediate
                structural parent), never every DOM ancestor.

        Returns:
            None - a write-only side effect. Replaces, not appends: a
            component rediscovered on a later page visit gets its
            containment refreshed the same way `record_component` refreshes
            its descriptive fields, not stacked with the previous visit's.
        Details: docs/dev/core/interfaces.md#record_component_ancestors
        """

    def get_containment_ledger(self, site: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """`{page_url: {path: [ancestor, ...]}}` for every component that
        has recorded containment. `{}` for a backend/site where
        `record_component_ancestors` was never called.
        Details: docs/dev/core/interfaces.md#get_containment_ledger
        """
        return {}
