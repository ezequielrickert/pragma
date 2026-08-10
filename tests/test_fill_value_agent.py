"""Regression tests for Phase 4 of the crawl4ai migration: AI-generated fill
values (src/crawlers/fill_value_agent.py).
"""
import asyncio
import http.server
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from src.core.interfaces import Agent
from src.crawlers.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from src.crawlers.fill_value_agent import (
    FILL_VALUE_SYSTEM_INSTRUCTION,
    generate_fill_value,
    make_ai_fill_value_fn,
)
from src.crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"


class RecordingAgent(Agent):
    """Returns each response in `script` in order (then repeats the last),
    recording every (prompt, system_instruction) pair it was called with -
    same shape as this project's existing ScriptedAgent/RecordingAgent test
    doubles (see wiki/debugging-agent-systems.md's "deterministic scripted
    fake" pattern)."""

    def __init__(self, script: List[str]) -> None:
        self.script = list(script)
        self.calls: List[Tuple[str, Optional[str]]] = []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls.append((prompt, system_instruction))
        idx = min(len(self.calls) - 1, len(self.script) - 1)
        return self.script[idx]


class RaisingAgent(Agent):
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        raise RuntimeError("simulated agent failure")


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


def test_generate_fill_value_uses_its_own_dedicated_system_instruction():
    """Per wiki/prompt-engineering-for-llm-agents.md Principle 1 - this call
    site's instruction must be its own, not shared/reused."""
    agent = RecordingAgent(["Jane Doe"])
    value = asyncio.run(generate_fill_value(agent, {"tag": "input", "input_type": "text", "label": "Full name"}, "A contact form"))
    assert value == "Jane Doe"
    assert len(agent.calls) == 1
    prompt, system_instruction = agent.calls[0]
    assert system_instruction == FILL_VALUE_SYSTEM_INSTRUCTION
    assert "Full name" in prompt
    assert "A contact form" in prompt


def test_generate_fill_value_strips_quotes_and_whitespace():
    agent = RecordingAgent(['  "test@example.com"  '])
    value = asyncio.run(generate_fill_value(agent, {"tag": "input", "input_type": "email"}))
    assert value == "test@example.com"


def test_generate_fill_value_falls_back_to_placeholder_on_agent_exception():
    agent = RaisingAgent()
    value = asyncio.run(generate_fill_value(agent, {"tag": "input", "input_type": "email"}))
    assert value == "test@example.com"  # fill_values.default_placeholder_fill_value's email case


def test_generate_fill_value_falls_back_to_placeholder_on_empty_response():
    agent = RecordingAgent(["   "])
    value = asyncio.run(generate_fill_value(agent, {"tag": "input", "input_type": "tel"}))
    assert value == "555-0100"


def test_mechanical_crawler_fills_with_ai_generated_value_end_to_end(fixture_server):
    """Full integration: MechanicalCrawler wired with an AI fill_value_fn
    (not the placeholder default) actually uses the agent's response for a
    real discovered field on a real crawl4ai-driven page.

    max_pages=15, not 1: index.html has an early navigating link ahead of its
    fillable field in DOM order, so (per mechanical_loop.py's own documented
    behavior) reaching the field takes more than one visit-pass - see
    test_mechanical_loop.py's module docstring for why."""
    agent = RecordingAgent(["Ada Lovelace"])

    async def run():
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0)) as crawler:
            mech = MechanicalCrawler(
                crawler,
                config=MechanicalCrawlerConfig(
                    max_pages=15,
                    fill_value_fn=make_ai_fill_value_fn(agent),
                ),
            )
            return await mech.crawl_site(f"{fixture_server}/index.html")

    results = asyncio.run(run())
    fill = next(
        i for r in results if r.url.endswith("index.html") for i in r.interactions if i.action == "fill"
    )
    assert fill.value == "Ada Lovelace"
    assert agent.calls  # the agent was actually consulted, not bypassed
