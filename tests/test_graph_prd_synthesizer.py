"""Regression tests for Phase 5 of the crawl4ai migration:
GraphPRDSynthesizer (generators/graph_prd_synthesizer.py).
"""
import asyncio
import http.server
import threading
from pathlib import Path
from typing import List, Optional

import pytest

from core.interfaces import Agent
from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from generators.graph_prd_synthesizer import (
    CATALOG_SYSTEM_INSTRUCTION,
    COMBINE_SYSTEM_INSTRUCTION,
    REDUCE_SYSTEM_INSTRUCTION,
    SYNTHESIS_SYSTEM_INSTRUCTION,
    _MAX_FACTS_PER_PAGE,
    _MAX_SECTIONS_PER_REDUCE,
    GraphPRDSynthesizer,
    _build_page_facts,
    _render_fact_line,
    build_mermaid_graph,
)
from database.ladybug.store import LadybugGraphStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"
SITE = "synth-test-site"


class RecordingAgent(Agent):
    """Fake agent that records every call and returns a response distinguishable
    by which stage asked for it - CATALOG (per-page narration), SYNTHESIS (per-batch
    summarize), or REDUCE (final combine) - so tests can assert not just that a call
    happened, but which stage it belonged to and what it saw.
    """

    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls.append((prompt, system_instruction))
        if system_instruction == CATALOG_SYSTEM_INSTRUCTION:
            return f"Narrated {len(self.calls)} component(s)."
        if system_instruction == SYNTHESIS_SYSTEM_INSTRUCTION:
            return f"Section summary #{len(self.calls)}."
        if system_instruction == COMBINE_SYSTEM_INSTRUCTION:
            return f"Combined chunk #{len(self.calls)}."
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
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("example.com", status="Finished", components=2, description="A test site.")
    store.record_component("example.com", "body > button#a", tag="button", text="Click me", component_type="button")
    store.record_component_interaction("example.com", "body > button#a", action="click", resulting_url="example.com")
    store.record_edge("example.com", "example.com/about", component="About link", action="click")

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)
    prd = synthesizer.synthesize(SITE)

    # One page (well under the batch_size default) still goes through all three
    # stages: catalog narration, one batch-summarize call, one reduce call.
    assert prd.startswith("# Digital Blueprint\n\nSynthesized report.")
    system_instructions = [c[1] for c in agent.calls]
    assert CATALOG_SYSTEM_INSTRUCTION in system_instructions
    assert SYNTHESIS_SYSTEM_INSTRUCTION in system_instructions
    assert REDUCE_SYSTEM_INSTRUCTION in system_instructions
    # The batch-summarize prompt must include the page's description.
    batch_prompt = next(p for p, si in agent.calls if si == SYNTHESIS_SYSTEM_INSTRUCTION)
    assert "A test site." in batch_prompt
    # The mermaid graph is appended to the returned document in code, not asked
    # of the model - it must never appear in any prompt sent to the agent.
    assert not any("flowchart LR" in prompt for prompt, _ in agent.calls)
    assert "flowchart LR" in prd


def test_synthesize_uses_its_own_dedicated_system_instructions_not_shared():
    """Per wiki/prompt-engineering-for-llm-agents.md Principle 1."""
    assert CATALOG_SYSTEM_INSTRUCTION != SYNTHESIS_SYSTEM_INSTRUCTION
    assert CATALOG_SYSTEM_INSTRUCTION != REDUCE_SYSTEM_INSTRUCTION
    assert SYNTHESIS_SYSTEM_INSTRUCTION != REDUCE_SYSTEM_INSTRUCTION


def test_narration_failure_on_one_page_does_not_abort_synthesis():
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("example.com", status="Finished", components=1)
    store.record_component("example.com", "body > button#a", tag="button", text="Click me", component_type="button")

    class FailingCatalogAgent(Agent):
        def generate(self, prompt, system_instruction=None):
            if system_instruction == CATALOG_SYSTEM_INSTRUCTION:
                raise RuntimeError("simulated narration failure")
            return "# Blueprint (degraded catalog still included)"

    synthesizer = GraphPRDSynthesizer(FailingCatalogAgent(), store)
    prd = synthesizer.synthesize(SITE)
    assert prd.startswith("# Blueprint (degraded catalog still included)")


def test_synthesize_batches_pages_when_over_batch_size():
    """Regression for the unbounded single-prompt crash (see
    docs/explicativos/avance-corridas-gemma-empanadapp.md): with more pages than
    batch_size, synthesis must issue multiple bounded batch-summarize calls plus
    one small reduce call over the condensed summaries - never one call that sees
    every page's raw facts at once.
    """
    store = LadybugGraphStore(SITE)
    store.connect()
    n_pages = 7
    for i in range(n_pages):
        url = f"example.com/page{i}"
        store.upsert_page(url, status="Finished", components=0, description=f"Page {i} description.")

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store, batch_size=3)
    prd = synthesizer.synthesize(SITE)

    batch_calls = [p for p, si in agent.calls if si == SYNTHESIS_SYSTEM_INSTRUCTION]
    reduce_calls = [p for p, si in agent.calls if si == REDUCE_SYSTEM_INSTRUCTION]

    # ceil(7 / 3) = 3 batch-summarize calls, exactly one reduce call.
    assert len(batch_calls) == 3
    assert len(reduce_calls) == 1

    # No single batch call saw every page - each is bounded to <= batch_size pages.
    for prompt in batch_calls:
        assert sum(f"Page {i} description." in prompt for i in range(n_pages)) <= 3

    # The reduce call consumes the already-condensed batch summaries, not the raw
    # per-page descriptions again - proves the "reduce" stage is genuinely smaller.
    reduce_prompt = reduce_calls[0]
    assert "Section summary #" in reduce_prompt
    assert "Page 0 description." not in reduce_prompt

    assert prd


def test_end_to_end_crawl_then_synthesize(fixture_server):
    """Full pipeline: MechanicalCrawler + GraphStoreSink populate a real
    graph from a real crawl4ai-driven crawl, then GraphPRDSynthesizer reads
    it back with no live crawl session involved at all."""
    site = "e2e-" + fixture_server.rsplit(":", 1)[1]
    store = LadybugGraphStore(site)
    store.connect()
    sink = GraphStoreSink(store)

    async def crawl():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, max_pages=15))
            return await mech.crawl_site(f"{fixture_server}/index.html")

    asyncio.run(crawl())

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)
    prd = synthesizer.synthesize(site)
    assert prd
    assert agent.calls  # synthesis actually consulted the agent


def test_choice_group_fact_includes_choices_and_no_leads_elsewhere_by_default():
    """A consolidated choice-group's fact must list every choice, but not
    fabricate a leads_elsewhere entry when no option's interaction actually
    navigated anywhere."""
    page_components = {
        "div#opt-small": {
            "text": "Small", "tag": "div", "interacted": True,
            "component_type": "list/menu option",
            "options": (
                [
                    {"path": "div#opt-small", "text": "Small", "selected": False},
                    {"path": "div#opt-large", "text": "Large", "selected": False},
                ],
                "sizeList",
            ),
            "interactions": [{"action": "click", "value": "", "resulting_url": ""}],
            "network_requests": [],
        },
    }
    facts, _truncated = _build_page_facts(page_components)
    assert len(facts) == 1
    fact = facts[0]
    assert fact["type"] == "choice group (dropdown/menu/radio/checkbox)"
    assert fact["choices"] == ["Small", "Large"]
    assert "leads_elsewhere" not in fact


def test_choice_group_fact_surfaces_an_option_that_navigates_differently():
    """The one fact this consolidated group of nodes must not lose: a
    specific option (recorded via source_path - see GraphStoreSink.
    _resolve_write_path) leading somewhere its siblings don't."""
    page_components = {
        "div#opt-small": {
            "text": "Small", "tag": "div", "interacted": True,
            "component_type": "list/menu option",
            "options": (
                [
                    {"path": "div#opt-small", "text": "Small", "selected": False},
                    {"path": "div#opt-large", "text": "Large", "selected": False},
                ],
                "sizeList",
            ),
            "interactions": [
                {
                    "action": "click", "value": "", "resulting_url": "example.com/large-details",
                    "source_path": "div#opt-large",
                },
            ],
            "network_requests": [],
        },
    }
    facts, _truncated = _build_page_facts(page_components)
    fact = facts[0]
    assert fact["leads_elsewhere"] == ["Large -> example.com/large-details"]

    line = _render_fact_line(1, fact)
    assert "leads_elsewhere=" in line
    assert "Large -> example.com/large-details" in line


def _component(text: str) -> dict:
    return {
        "text": text, "tag": "button", "interacted": False, "component_type": "button",
        "options": ([], ""), "interactions": [], "network_requests": [],
    }


def test_build_page_facts_caps_at_the_limit_and_reports_truncation():
    """The map stage's own unbounded surface, per wiki/local-and-small-
    model-constraints.md's checklist: a real page can carry 100-300+ raw
    components with no other bound on how many reach the narration prompt."""
    page_components = {f"button#{i}": _component(f"Button {i}") for i in range(_MAX_FACTS_PER_PAGE + 20)}

    facts, truncated = _build_page_facts(page_components)

    assert len(facts) == _MAX_FACTS_PER_PAGE
    assert truncated is True


def test_build_page_facts_under_the_limit_is_not_truncated():
    page_components = {"button#a": _component("A")}

    facts, truncated = _build_page_facts(page_components)

    assert len(facts) == 1
    assert truncated is False


def test_narrate_page_catalog_notes_truncation_in_the_prompt():
    store = LadybugGraphStore(SITE)
    store.connect()
    for i in range(_MAX_FACTS_PER_PAGE + 5):
        store.record_component("example.com/big-page", f"button#{i}", tag="button", text=f"Button {i}")

    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)
    synthesizer._narrate_page_catalog()

    catalog_prompt = next(p for p, si in agent.calls if si == CATALOG_SYSTEM_INSTRUCTION)
    assert f"capped at {_MAX_FACTS_PER_PAGE}" in catalog_prompt


def test_reduce_combines_in_chunks_when_sections_exceed_the_cap():
    """The reduce stage's own unbounded surface: a 200-page site at the
    default batch_size=5 produces 40 sections, which the un-chunked
    version joined unconditionally into one prompt - exactly the second
    recursive instance of the bug this whole map-reduce split exists to
    prevent."""
    store = LadybugGraphStore(SITE)
    store.connect()
    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)

    sections = [f"Section {i} summary." for i in range(_MAX_SECTIONS_PER_REDUCE * 2 + 1)]
    synthesizer._reduce(SITE, sections)

    system_instructions = [si for _, si in agent.calls]
    assert COMBINE_SYSTEM_INSTRUCTION in system_instructions
    # Exactly one *final* reduce call, however many sections started - the
    # whole point of chunking first.
    assert system_instructions.count(REDUCE_SYSTEM_INSTRUCTION) == 1

    # No call - combine or final reduce - ever saw more than the cap's
    # worth of section summaries at once.
    for prompt, si in agent.calls:
        if si in (COMBINE_SYSTEM_INSTRUCTION, REDUCE_SYSTEM_INSTRUCTION):
            assert prompt.count("Section ") <= _MAX_SECTIONS_PER_REDUCE * 2  # header text + separators, generous bound


def test_reduce_under_the_cap_skips_chunking_entirely():
    store = LadybugGraphStore(SITE)
    store.connect()
    agent = RecordingAgent()
    synthesizer = GraphPRDSynthesizer(agent, store)

    sections = [f"Section {i} summary." for i in range(3)]
    synthesizer._reduce(SITE, sections)

    system_instructions = [si for _, si in agent.calls]
    assert COMBINE_SYSTEM_INSTRUCTION not in system_instructions
    assert system_instructions == [REDUCE_SYSTEM_INSTRUCTION]
