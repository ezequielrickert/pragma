"""Import all plugin modules so their registrations run.
Details: docs/dev/core/bootstrap.md#module
"""
from __future__ import annotations

from agents import local_agent  # noqa: F401  (registers "local")
from agents import mock_agent  # noqa: F401  (registers "mock")
from generators import component_catalog  # noqa: F401  (registers "catalog", "catalog-data")
from generators import component_tree  # noqa: F401  (registers "tree")
from generators import coverage  # noqa: F401  (registers "coverage")
from generators import gherkin  # noqa: F401  (registers "gherkin", "sequences")
from generators import graph_export  # noqa: F401  (registers "export")
from generators import graph_prd_synthesizer  # noqa: F401  (registers "prd")
from generators import openapi  # noqa: F401  (registers "openapi")
from generators import usability  # noqa: F401  (registers "usability")
from generators import user_flows  # noqa: F401  (registers "flows")
from database.ladybug import store as ladybug_store  # noqa: F401  (registers "ladybug", "memory")
