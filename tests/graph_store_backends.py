"""Per-backend setup for the `GraphStore` conformance suite
(`test_graph_store_conformance.py`). Each entry in `BACKENDS` pairs a name
with a zero-arg `resolve()` that returns a connected `GraphStore` instance,
or `None` when that backend isn't available in the current environment
(missing driver, no server reachable and no Docker to start one, ...).

The conformance suite never imports a backend module directly - adding a
fourth backend (e.g. `duckdb`) is entirely: write the module, add one
factory function here, add one line to `BACKENDS`. No test changes.
"""
from __future__ import annotations

import atexit
import os
from typing import Callable, Dict, Optional

from core.interfaces import GraphStore


def _memory_backend() -> Optional[GraphStore]:
    from database.memory_graph_store import InMemoryGraphStore

    return InMemoryGraphStore()


def _existing_neo4j_reachable() -> bool:
    """Tier 1 - the fast path, no container startup at all."""
    try:
        from database.neo4j_graph_store import Neo4jGraphStore

        probe = Neo4jGraphStore()
        probe.connect()
        probe.close()
        return True
    except Exception:
        return False


# Memoized across the whole pytest session - resolving tier 2 starts an
# ephemeral container, which must happen at most once per run, not once per
# test. `_resolved` (not just `_kwargs is not None`) distinguishes "not
# checked yet" from "checked, nothing available" so a `None` result is
# cached too instead of re-probing Docker on every single test.
_neo4j_kwargs: Optional[Dict[str, object]] = None
_neo4j_resolved = False


def _start_ephemeral_neo4j_container() -> Optional[Dict[str, object]]:
    """Tier 2 - an ephemeral `testcontainers`-managed instance, torn down at
    interpreter exit via `atexit` (there is no pytest session-fixture scope
    to hang the teardown off here, since this module is a plain helper
    shared by fixtures, not a fixture itself).
    """
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs
    except ImportError:
        return None

    password = "pragma-test-container"  # nosec - throwaway, ephemeral container, never persisted
    container = None
    try:
        # Constructing DockerContainer (not just .start()) can itself raise:
        # it eagerly talks to the Docker client, so "Docker installed but the
        # daemon isn't running" fails right here, before .start() is reached.
        container = (
            DockerContainer("neo4j:5.24-community")  # same image pinned in docker-compose.yml
            .with_env("NEO4J_AUTH", f"neo4j/{password}")
            .with_exposed_ports(7687)
        )
        container.start()
        wait_for_logs(container, "Bolt enabled on", timeout=90)
    except Exception:
        # Docker installed but the daemon unreachable, image pull failed, or
        # the container never became ready in time - same end result as "no
        # Neo4j available" (tier 3), not a hard failure.
        if container is not None:
            try:
                container.stop()
            except Exception:
                pass
        return None

    atexit.register(container.stop)
    return {
        "host": container.get_container_host_ip(),
        "port": int(container.get_exposed_port(7687)),
        "user": "neo4j",
        "password": password,
        "database": "neo4j",
    }


def resolve_neo4j_connection() -> Optional[Dict[str, object]]:
    """Public: also used directly by `test_neo4j_graph_store_integration.py`,
    which needs the raw connection kwargs (not a `GraphStore` instance) to
    build its own `store` fixture around backend-specific assertions.
    """
    global _neo4j_kwargs, _neo4j_resolved
    if _neo4j_resolved:
        return _neo4j_kwargs
    _neo4j_resolved = True

    if _existing_neo4j_reachable():
        _neo4j_kwargs = {
            "host": os.getenv("NEO4J_HOST", "localhost"),
            "port": int(os.getenv("NEO4J_PORT", "7687")),
            "user": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD"),
            "database": os.getenv("NEO4J_DATABASE", "neo4j"),
        }
        return _neo4j_kwargs

    _neo4j_kwargs = _start_ephemeral_neo4j_container()
    return _neo4j_kwargs


def _neo4j_backend() -> Optional[GraphStore]:
    kwargs = resolve_neo4j_connection()
    if kwargs is None:
        return None
    from database.neo4j_graph_store import Neo4jGraphStore

    store = Neo4jGraphStore(**kwargs)
    store.connect()
    return store


BACKENDS: Dict[str, Callable[[], Optional[GraphStore]]] = {
    "memory": _memory_backend,
    "neo4j": _neo4j_backend,
}
