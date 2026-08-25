"""Basic import/registry sanity checks for the crawl4ai-based pipeline.

Everything this file used to cover about the old per-step LLM decision loop
(GOTO/CLICK/FINISH parsing, the JSON action grammar, tool-schema enums,
StubScraper/ScriptedAgent-driven SimplePRDGenerator runs) tested mechanisms
that no longer exist (`core/interfaces.py`'s docstring explains why) -
replaced by the engine-core/graph-sink test files: tests/test_engine_core.py,
tests/test_graph_sink.py, tests/test_fill_value_agent.py.
`generators.graph_prd_synthesizer` itself was later retired in full
(docs/adr/0009 point 4, ticket #104) - replaced by the deterministic
`generators.requirements`, its own module tested in tests/test_requirements.py.
`core/engine.py` (the Legacy Engine) and its own `mechanical_loop`/
`page_visitor` worker loop were retired outright, not replaced in kind
(issue #242) - `spiders.orchestration.engine_core` is the one shared core
every phase command sits on now.
"""
import importlib

from core import bootstrap  # noqa: F401
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def test_imports():
    importlib.import_module("core.interfaces")
    importlib.import_module("core.docs_engine")
    importlib.import_module("spiders.browser.crawl4ai_crawler")
    importlib.import_module("spiders.orchestration.page_interaction")
    importlib.import_module("spiders.orchestration.deep_crawl_strategy")
    importlib.import_module("spiders.orchestration.engine_core")
    importlib.import_module("spiders.orchestration.graph_sink")
    importlib.import_module("spiders.content.fill_value_agent")
    importlib.import_module("generators.requirements")


def test_registries_populated():
    assert "mock" in AGENT_REGISTRY.names()
    assert "memory" in GRAPH_STORE_REGISTRY.names()
