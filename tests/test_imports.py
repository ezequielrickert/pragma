"""Basic import/registry sanity checks for the crawl4ai-based pipeline.

Everything this file used to cover about the old per-step LLM decision loop
(GOTO/CLICK/FINISH parsing, the JSON action grammar, tool-schema enums,
StubScraper/ScriptedAgent-driven SimplePRDGenerator runs) tested mechanisms
that no longer exist (`core/interfaces.py`'s docstring explains why) -
replaced by the mechanical-loop/graph-sink test files:
tests/test_mechanical_loop.py, tests/test_graph_sink.py,
tests/test_fill_value_agent.py. `generators.graph_prd_synthesizer` itself
was later retired in full (docs/adr/0009 point 4, ticket #104) - replaced
by the deterministic `generators.requirements`, its own module tested in
tests/test_requirements.py.
"""
import importlib

from core import bootstrap  # noqa: F401
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def test_imports():
    importlib.import_module("core.interfaces")
    importlib.import_module("core.engine")
    importlib.import_module("spiders.browser.crawl4ai_crawler")
    importlib.import_module("spiders.orchestration.mechanical_loop")
    importlib.import_module("spiders.orchestration.graph_sink")
    importlib.import_module("spiders.content.fill_value_agent")
    importlib.import_module("generators.requirements")


def test_registries_populated():
    assert "mock" in AGENT_REGISTRY.names()
    assert "memory" in GRAPH_STORE_REGISTRY.names()
