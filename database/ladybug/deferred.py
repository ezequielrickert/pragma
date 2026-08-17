"""Temporary no-op stand-ins for the three write methods
`spiders/orchestration/graph_sink/sink.py` still calls that storage-
migration plan steps 7-8 have not yet built: `Option`/`HAS_OPTION` (step
8), `Container`/`CONTAINS` (step 8), and `Request`/`Endpoint`/`Payload`
(step 7, the API-contract redesign).

Why stubs rather than leaving the sink's calls unhandled: step 6 wires
`GraphStoreSink` straight to `LadybugGraphStore` with no DuckDB fallback
left - a real crawl calling an attribute that doesn't exist at all would
crash outright, not just lose the data those three calls were recording.
A documented no-op is the same "optional capability a backend may not
implement" discipline the retired `_containment_interface.py`/
`_page_extras_interface.py` already used for exactly this situation
(non-abstract methods with a default no-op body).

**Every method here is a placeholder.** Options, structural containment,
and component-triggered network requests are silently not captured
between step 6 landing and steps 7-8 landing - this module's own
existence is the tracking mechanism for that gap; delete it the moment
all three real implementations exist.

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

    def record_component_network(self, page_url: str, path: str, requests: List[Dict[str, Any]]) -> None:
        """Placeholder for step 7's `Request`/`Endpoint`/`Payload` write
        path - does nothing yet.
        Details: docs/dev/database/ladybug/deferred.md#record_component_network
        """

    def record_page_network(self, page_url: str, requests: List[Dict[str, Any]]) -> None:
        """Placeholder for step 7's `Request`/`Endpoint`/`Payload` write
        path (the page-load half - `LOADED` rather than `TRIGGERED`) -
        does nothing yet.
        Details: docs/dev/database/ladybug/deferred.md#record_page_network
        """

    def get_page_network_ledger(self) -> Dict[str, List[Dict[str, Any]]]:
        """Placeholder read for `record_page_network` above - always
        empty, since nothing is ever written there yet. Lets
        `Engine._apply_request_graph` keep running unmodified: with no
        network data to cluster, `build_inferred_requests` returns `[]`
        rather than the pass needing to be specially skipped.
        Details: docs/dev/database/ladybug/deferred.md#get_page_network_ledger
        """
        return {}

    def record_inferred_requests(self, requests: List[Any]) -> None:
        """Placeholder for step 7's `Endpoint`/`DERIVED_FROM` write path -
        does nothing yet (there is nothing to record while
        `get_page_network_ledger` never returns any network data).
        Details: docs/dev/database/ladybug/deferred.md#record_inferred_requests
        """

    def get_inferred_requests(self) -> List[Any]:
        """Placeholder read for `record_inferred_requests` above - always
        empty. `openapi.py`/`coverage.py`/`usability.py` all read this
        defensively already (an empty list is a normal "nothing inferred
        yet" case, not a special one), so they report zero endpoints
        rather than crashing until step 7 lands.
        Details: docs/dev/database/ladybug/deferred.md#get_inferred_requests
        """
        return []
