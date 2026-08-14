"""AI-generated fill values for mechanically-discovered form fields.
Details: docs/dev/spiders/content/fill_value_agent.md#module
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

from core.interfaces import Agent
from .fill_values import default_placeholder_fill_value

# Narrowly-scoped on purpose - never reused elsewhere.
# Details: docs/dev/spiders/content/fill_value_agent.md#fill_value_system_instruction
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
    """Ask `agent` for a plausible value for `component`; never raises.
    Details: docs/dev/spiders/content/fill_value_agent.md#generate_fill_value
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
    """Bind `agent` into a `fill_value_fn` closure for `MechanicalCrawlerConfig`.
    Details: docs/dev/spiders/content/fill_value_agent.md#make_ai_fill_value_fn
    """

    async def fill_value_fn(component: Dict[str, Any], page_description: str) -> str:
        return await generate_fill_value(agent, component, page_description)

    return fill_value_fn
