"""Per-backend setup for the `GraphStore` conformance suite
(`test_graph_store_conformance.py`). Each entry in `BACKENDS` pairs a name
with a zero-arg `resolve()` that returns a connected `GraphStore` instance,
or `None` when that backend isn't available in the current environment
(e.g. an optional driver not installed).

The conformance suite never imports a backend module directly - adding
another backend is entirely: write the module, add one factory function
here, add one line to `BACKENDS`. No test changes.

This file used to also resolve a Neo4j connection (existing instance, or
an ephemeral `testcontainers`-managed one) before that backend was retired
- see git history if a third, server-backed backend ever needs the same
tiered-resolution shape again.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from core.interfaces import GraphStore


def _memory_backend() -> Optional[GraphStore]:
    from database.memory_graph_store import InMemoryGraphStore

    return InMemoryGraphStore()


def _duckdb_backend() -> Optional[GraphStore]:
    try:
        from database.duckdb_graph_store import DuckDBGraphStore
    except ImportError:
        return None  # duckdb not installed - an optional dependency

    store = DuckDBGraphStore()
    store.connect()
    return store


BACKENDS: Dict[str, Callable[[], Optional[GraphStore]]] = {
    "memory": _memory_backend,
    "duckdb": _duckdb_backend,
}
