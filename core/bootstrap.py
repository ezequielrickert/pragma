"""Import all plugin modules so their registrations run.
Details: docs/dev/core/bootstrap.md#module
"""
from __future__ import annotations

from agents import local_agent  # noqa: F401  (registers "local")
from agents import mock_agent  # noqa: F401  (registers "mock")
from generators import accessibility  # noqa: F401  (registers "accessibility")
from generators import architecture_map  # noqa: F401  (registers "architecture")
from generators import aria_tree  # noqa: F401  (registers "tree")
from generators import component_catalog  # noqa: F401  (registers "catalog", "catalog-data")
from generators import coverage  # noqa: F401  (registers "coverage")
from generators import data_model  # noqa: F401  (registers "data-model")
from generators import design_tokens  # noqa: F401  (registers "tokens")
from generators import gherkin  # noqa: F401  (registers "gherkin", "sequences")
from generators import graph_export  # noqa: F401  (registers "export")
from generators import graph_prd_synthesizer  # noqa: F401  (registers "prd")
from generators import openapi  # noqa: F401  (registers "openapi")
from generators import usability  # noqa: F401  (registers "usability")
from generators import user_flows  # noqa: F401  (registers "flows")
from database.ladybug import store as ladybug_store  # noqa: F401  (registers "ladybug", "memory")
