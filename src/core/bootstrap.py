"""Import all plugin modules so their registrations run.

Import this module once (from the CLI or tests) before using the registries.
Optional-dependency plugins are guarded so a missing package never breaks startup.

Post-crawl4ai-migration: `src/crawlers/` (`Crawl4AICrawler`, `MechanicalCrawler`,
`GraphStoreSink`) is wired directly by `Engine`, not through a registry - there's
exactly one crawling implementation now, unlike agents/graph stores which
genuinely have multiple.
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
