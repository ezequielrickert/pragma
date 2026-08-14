"""Basic import/registry sanity checks for the crawl4ai-based pipeline.

Everything this file used to cover about the old per-step LLM decision loop
(GOTO/CLICK/FINISH parsing, the JSON action grammar, tool-schema enums,
StubScraper/ScriptedAgent-driven SimplePRDGenerator runs) tested mechanisms
that no longer exist (`core/interfaces.py`'s docstring explains why) -
replaced by the mechanical-loop/graph-sink/synthesizer test files:
tests/test_mechanical_loop.py, tests/test_graph_sink.py,
tests/test_fill_value_agent.py, tests/test_graph_prd_synthesizer.py.
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
    importlib.import_module("generators.graph_prd_synthesizer")


def test_registries_populated():
    assert "mock" in AGENT_REGISTRY.names()
    assert "memory" in GRAPH_STORE_REGISTRY.names()
