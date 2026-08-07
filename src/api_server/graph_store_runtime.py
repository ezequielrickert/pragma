"""Lazily provides the single, process-lifetime `Neo4jGraphStore` used by `/components/*`.

Mirrors `playwright_runtime.py`'s singleton pattern, but simpler: the Neo4j driver is
thread-safe for concurrent sessions (unlike Playwright's sync API, which is bound to one
OS thread), so no dedicated executor is needed here - FastAPI's default sync-endpoint
threadpool is fine.

Read-only by design: this module exists so `/components/*` can answer "what does the
persisted component checklist say" without depending on `SimplePRDGenerator` or any other
part of Module 2 - it only ever calls `GraphStore` query methods, never `record_*`.
"""
from __future__ import annotations

from typing import Optional

from ..storage.neo4j_graph_store import Neo4jGraphStore

_store: Optional[Neo4jGraphStore] = None


def get_store() -> Neo4jGraphStore:
    """Lazily create and connect the singleton. Raises whatever `connect()` raises
    (e.g. missing `NEO4J_PASSWORD`, unreachable host) - callers turn that into a
    clear HTTP error rather than a bare 500 (see `components.py`)."""
    global _store
    if _store is None:
        store = Neo4jGraphStore()
        store.connect()
        _store = store
    return _store
