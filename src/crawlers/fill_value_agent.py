"""Phase 4 of the crawl4ai migration: AI-generated fill values for
mechanically-discovered form fields - the one AI call that happens *during*
the mechanical crawl itself (every other AI use is post-hoc, Phase 5).

`FILL_VALUE_SYSTEM_INSTRUCTION` is its own, narrowly-scoped instruction - per
wiki/prompt-engineering-for-llm-agents.md Principle 1 ("never share a
system_instruction across semantically different calls"), it is not reused
from anywhere else, and nothing else should reuse it either: its only job is
"given one field's metadata, return one plausible value," nothing about
narration, synthesis, or any other call site this migration adds.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

from ..core.interfaces import Agent
from .fill_values import default_placeholder_fill_value

FILL_VALUE_SYSTEM_INSTRUCTION = (
    "You generate one plausible, realistic value to type into a single web form field, "
    "given that field's own metadata and the page's short description for context. "
    "Respond with ONLY the value itself on a single line - no quotes, no explanation, "
    "no markdown, nothing else before or after it."
)


def _build_prompt(component: Dict[str, Any], page_description: str) -> str:
    lines = [
        f"Field tag: {component.get('tag', '')}",
        f"Field type: {component.get('input_type', '') or '(none)'}",
        f"Placeholder: {component.get('placeholder', '') or '(none)'}",
        f"Label: {component.get('label', '') or '(none)'}",
        f"Name attribute: {component.get('name', '') or '(none)'}",
    ]
    if page_description:
        lines.append(f"Page context: {page_description}")
    lines.append("Value:")
    return "\n".join(lines)


async def generate_fill_value(agent: Agent, component: Dict[str, Any], page_description: str = "") -> str:
    """Ask `agent` for a plausible value for `component`.

    `Agent.generate()` is a synchronous call (most backends are blocking
    HTTP requests; local ones can be genuinely slow - see
    wiki/local-and-small-model-constraints.md's generous-timeout guidance) -
    run via `asyncio.to_thread` so a live AI call never blocks the mechanical
    crawl's own event loop while it waits, and other pages' work isn't
    serialized behind it unnecessarily.

    Falls back to `default_placeholder_fill_value` - never raises up into the
    caller - on any agent failure or an empty/unusable response, matching
    wiki/local-and-small-model-constraints.md's "recover, don't error" guidance
    for a parameter the model might mishandle: one bad or slow model response
    must not abort an otherwise-mechanical crawl.
    """
    prompt = _build_prompt(component, page_description)
    try:
        raw = await asyncio.to_thread(agent.generate, prompt, FILL_VALUE_SYSTEM_INSTRUCTION)
    except Exception:
        return await default_placeholder_fill_value(component, page_description)
    value = (raw or "").strip().strip('"').strip("'")
    if not value:
        return await default_placeholder_fill_value(component, page_description)
    return value


def make_ai_fill_value_fn(agent: Agent) -> Callable[[Dict[str, Any], str], Awaitable[str]]:
    """Bind `agent` into a `fill_value_fn` closure matching
    `MechanicalCrawler`'s expected `(component, page_description) -> str`
    signature - the convenience constructor callers pass to
    `MechanicalCrawler(fill_value_fn=make_ai_fill_value_fn(my_agent))`.
    """

    async def fill_value_fn(component: Dict[str, Any], page_description: str) -> str:
        return await generate_fill_value(agent, component, page_description)

    return fill_value_fn
