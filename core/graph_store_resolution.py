"""Shared `graph_store` resolution: create and connect the configured
backend, falling back to an in-memory store on a genuine failure - except
a cross-process `SiteLockError`, which must propagate rather than being
silently swallowed into a throwaway store (that would defeat the entire
point of the lock: a caller thinking it's writing to the real site
database while actually crawling into a store nobody will ever read).

This exact create-connect-fallback shape was duplicated verbatim across
`Engine`/`StaticEngine`/`DynamicEngine.from_config` before the lock
existed; factored out once it did, since a fourth copy - or a future
edit to one of the three - that forgot the `SiteLockError` guard would
silently reintroduce the failure mode this module exists to prevent.
`ClusterEngine`/`DocsEngine.from_config` don't use this: neither had a
fallback-to-memory branch to begin with, so an unguarded `connect()`
already propagates any error, `SiteLockError` included, with nothing to
special-case.
Details: docs/dev/core/graph_store_resolution.md#module
"""
from __future__ import annotations

from typing import Any, Dict

from database.ladybug.site_lock import SiteLockError
from .registry import GRAPH_STORE_REGISTRY


def resolve_graph_store(graph_store_name: str, site: str, store_options: Dict[str, Any]) -> Any:
    """Create and connect `graph_store_name` for `site`, falling back to
    the `"memory"` backend if that fails - unless the failure is a
    `SiteLockError`, which is re-raised unchanged.
    Details: docs/dev/core/graph_store_resolution.md#resolve_graph_store
    """
    try:
        graph_store = GRAPH_STORE_REGISTRY.create(graph_store_name, site=site, **store_options)
        graph_store.connect()
        return graph_store
    except SiteLockError:
        raise
    except Exception as exc:
        print(f"Failed to initialize {graph_store_name} graph store: {exc}; falling back to memory")
        graph_store = GRAPH_STORE_REGISTRY.create("memory", site=site)
        graph_store.connect()
        return graph_store
