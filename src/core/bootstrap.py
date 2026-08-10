"""Import all plugin modules so their registrations run.
Details: docs/dev/core/bootstrap.md#module
"""
from __future__ import annotations

from ..agents import local_agent  # noqa: F401  (registers "local")
from ..agents import mock_agent  # noqa: F401  (registers "mock")
from ..storage import memory_graph_store  # noqa: F401  (registers "memory")

try:
    from ..agents import providers  # noqa: F401  (registers "gemini", "openai")
except ImportError as exc:
    print(f"Optional agent providers unavailable: {exc}")

try:
    from ..storage import neo4j_graph_store  # noqa: F401  (registers "neo4j")
except ImportError as exc:
    print(f"Optional graph store providers unavailable: {exc}")
