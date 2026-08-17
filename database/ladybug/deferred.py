"""Temporary no-op stand-ins for the two write methods
`spiders/orchestration/graph_sink/sink.py` still calls that storage-
migration plan step 8 has not yet built: `Option`/`HAS_OPTION` and
`Container`/`CONTAINS`. Step 7's own three placeholders
(`record_component_network`, `record_page_network`,
`get_page_network_ledger`/`record_inferred_requests`/
`get_inferred_requests`) are gone - `network.py` implements them for real.

Why stubs rather than leaving the sink's calls unhandled: step 6 wires
`GraphStoreSink` straight to `LadybugGraphStore` with no DuckDB fallback
left - a real crawl calling an attribute that doesn't exist at all would
crash outright, not just lose the data these two calls were recording.
A documented no-op is the same "optional capability a backend may not
implement" discipline the retired `_containment_interface.py`/
`_page_extras_interface.py` already used for exactly this situation
(non-abstract methods with a default no-op body).

**Every method here is a placeholder.** Options and structural
containment are silently not captured until step 8 lands - this module's
own existence is the tracking mechanism for that gap; delete it the
moment both real implementations exist.

Details: docs/dev/database/ladybug/deferred.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class _LadybugDeferredMixin:
    """Details: docs/dev/database/ladybug/deferred.md#_ladybugdeferredmixin"""

    def record_component_options(
        self, page_url: str, path: str, options: Dict[str, Any], option_labels: Optional[List[str]] = None,
    ) -> None:
        """Placeholder for step 8's `Option`/`HAS_OPTION` write path -
        does nothing yet. A stepper/choice-group/revealed-options control
        is still recorded as a plain `Component` (via `record_component`/
        `record_components`), just without its member options attached.
        Details: docs/dev/database/ladybug/deferred.md#record_component_options
        """

    def record_component_ancestors(self, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Placeholder for step 8's `Container`/`CONTAINS` write path -
        does nothing yet.
        Details: docs/dev/database/ladybug/deferred.md#record_component_ancestors
        """
