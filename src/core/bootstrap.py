"""Import all plugin modules so their registrations run.

Import this module once (from the CLI or tests) before using the registries.
Optional-dependency plugins are guarded so a missing package never breaks startup.
"""
from __future__ import annotations

from ..agents import local_agent  # noqa: F401  (registers "local")
from ..agents import mock_agent  # noqa: F401  (registers "mock")
from ..generators import prd_generator  # noqa: F401  (registers "simple")
from ..scrapers import playwright_scraper  # noqa: F401  (registers "playwright")

try:
    from ..agents import providers  # noqa: F401  (registers "gemini", "openai")
except ImportError as exc:
    print(f"Optional agent providers unavailable: {exc}")
