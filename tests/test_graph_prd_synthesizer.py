"""Regression tests for Phase 5 of the crawl4ai migration:
GraphPRDSynthesizer (src/generators/graph_prd_synthesizer.py).
"""
import asyncio
import http.server
import threading
from pathlib import Path
from typing import List, Optional

import pytest

from src.core.interfaces import Agent
from src.crawlers.crawl4ai_crawler import Crawl4AICrawler
from src.crawlers.graph_sink import GraphStoreSink
from src.crawlers.mechanical_loop import MechanicalCrawler
from src.generators.graph_prd_synthesizer import (
    CATALOG_SYSTEM_INSTRUCTION,
    SYNTHESIS_SYSTEM_INSTRUCTION,
    GraphPRDSynthesizer,
    build_mermaid_graph,
)
from src.storage.memory_graph_store import InMemoryGraphStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"
SITE = "synth-test-site"


class RecordingAgent(Agent):
    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls.append((prompt, system_instruction))
        if system_instruction == CATALOG_SYSTEM_INSTRUCTION:
            return f"Narrated {len(self.calls)} component(s)."
        return "# Digital Blueprint\n\nSynthesized report."


@pytest.fixture(scope="module")
def fixture_server():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(FIXTURE_DIR), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()


def test_build_mermaid_graph_renders_edges():
    edges = [{"from": "a.com", "to": "a.com/b", "component": "nav link", "action": "click"}]
    mermaid = build_mermaid_graph(edges)
    assert "flowchart LR" in mermaid
    assert "a.com" in mermaid and "a.com/b" in mermaid
    assert "nav link" in mermaid


def test_synthesize_reads_from_graph_store_with_no_live_crawl():
    """The whole point of Phase 5: synthesis works against a graph populated
    at some earlier, unrelated time - it needs nothing but the store."""
    store = InMemoryGraphStore()
    store.connect()
    store.upsert_page(SITE, "example.com", status="Finished", components=2, description="A test site.")
    store.record_component(SITE, "example.com", "body > button#a", tag="button", text="Click me", component_type="button")
    store.record_component_interaction(SITE, "example.com", "body > button#a", action="click", resulting_url="example.com")
    store.record_edge(SITE, "example.com", "example.com/about", component="About link", action="click")

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)
    prd = synthesizer.synthesize(SITE)

    assert prd == "# Digital Blueprint\n\nSynthesized report."
    # Two calls: one catalog narration (the page has a component), one final synthesis.
    system_instructions = [c[1] for c in agent.calls]
    assert CATALOG_SYSTEM_INSTRUCTION in system_instructions
    assert SYNTHESIS_SYSTEM_INSTRUCTION in system_instructions
    # The final synthesis prompt must include the page's description and the mermaid graph.
    final_prompt = next(p for p, si in agent.calls if si == SYNTHESIS_SYSTEM_INSTRUCTION)
    assert "A test site." in final_prompt
    assert "flowchart LR" in final_prompt


def test_synthesize_uses_its_own_dedicated_system_instructions_not_shared():
    """Per wiki/prompt-engineering-for-llm-agents.md Principle 1."""
    assert CATALOG_SYSTEM_INSTRUCTION != SYNTHESIS_SYSTEM_INSTRUCTION


def test_narration_failure_on_one_page_does_not_abort_synthesis():
    store = InMemoryGraphStore()
    store.connect()
    store.upsert_page(SITE, "example.com", status="Finished", components=1)
    store.record_component(SITE, "example.com", "body > button#a", tag="button", text="Click me", component_type="button")

    class FailingCatalogAgent(Agent):
        def generate(self, prompt, system_instruction=None):
            if system_instruction == CATALOG_SYSTEM_INSTRUCTION:
                raise RuntimeError("simulated narration failure")
            return "# Blueprint (degraded catalog still included)"

    synthesizer = GraphPRDSynthesizer(FailingCatalogAgent(), store)
    prd = synthesizer.synthesize(SITE)
    assert prd == "# Blueprint (degraded catalog still included)"


def test_end_to_end_crawl_then_synthesize(fixture_server):
    """Full pipeline: MechanicalCrawler + GraphStoreSink populate a real
    graph from a real crawl4ai-driven crawl, then GraphPRDSynthesizer reads
    it back with no live crawl session involved at all."""
    store = InMemoryGraphStore()
    store.connect()
    site = "e2e-" + fixture_server.rsplit(":", 1)[1]
    sink = GraphStoreSink(store, site)

    async def crawl():
        async with Crawl4AICrawler(wait_seconds=0) as crawler:
            mech = MechanicalCrawler(crawler, sink=sink, max_pages=15)
            return await mech.crawl_site(f"{fixture_server}/index.html")

    asyncio.run(crawl())

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)
    prd = synthesizer.synthesize(site)
    assert prd
    assert agent.calls  # synthesis actually consulted the agent
