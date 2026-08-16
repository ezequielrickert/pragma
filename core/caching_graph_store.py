"""Memoizes whole-site `GraphStore` reads for the read-only "post-crawl"
phase of one `Engine` run: whole-site passes (`_apply_component_families`,
`_apply_request_graph`, `_apply_graph_projection`) plus document
generation all read the same handful of whole-site tables independently -
`get_component_ledger` alone was called ~8 times per run (once per
generator that needs it, plus twice more in `Engine`'s own post-crawl
passes), each a fresh full materialization.

Safe specifically because of *when* this wraps: the crawl has already
finished writing by the time `Engine._run_async` constructs this (see its
own call site) - none of the writes the wrapped whole-site passes still
make (`record_component_families`, `record_inferred_requests`,
`record_page_metrics`, `record_page_modules`, ...) touch any of the tables
this caches, so a cached read can never go stale mid-run. This is not a
general-purpose GraphStore cache and must not be reused earlier in a run,
while the crawl is still writing to the tables it memoizes.

Details: docs/dev/core/caching_graph_store.md#module
"""
from __future__ import annotations

from typing import Any, Dict

from .interfaces import GraphStore

# Whole-site, site-only-argument reads confirmed to be called more than
# once per run across the generators + Engine's own post-crawl passes.
# Deliberately not every `get_*` method: a parameterized read like
# `get_page_label(site, url)` varies per call and isn't safe to memoize
# the same simple way, and a read called only once buys nothing from
# caching.
_CACHED_READS = (
    "get_component_ledger",
    "get_edges",
    "get_progress_table_rows",
    "get_text_content_ledger",
    "get_component_families",
    "get_inferred_requests",
    "get_page_measurements",
    "get_accessibility_violations",
    "get_page_metadata",
    "get_page_network_ledger",
    "get_stylesheets",
    "get_containment_ledger",
    "get_page_metrics",
    "get_page_modules",
)


class CachingGraphStore:
    """Wraps a `GraphStore`, memoizing `_CACHED_READS` per `(method, site)`.
    Every other method - reads and writes alike - passes straight through
    to the wrapped store via `__getattr__`; this class defines no method
    of its own with the same name as anything on `GraphStore`, so normal
    attribute lookup only ever finds this class's `__init__`/`__getattr__`
    and falls through correctly.
    """

    def __init__(self, inner: GraphStore) -> None:
        self._inner = inner
        self._cache: Dict[str, Dict[str, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        if name in _CACHED_READS:
            return lambda site: self._cached_call(name, site)
        return getattr(self._inner, name)

    def _cached_call(self, method_name: str, site: str) -> Any:
        per_method = self._cache.setdefault(method_name, {})
        if site not in per_method:
            per_method[site] = getattr(self._inner, method_name)(site)
        return per_method[site]
