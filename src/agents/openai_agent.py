"""
OpenAI agent implementation for Pragma.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from ..core.interfaces import Agent


@dataclass
class OpenAIConfig:
    """Every setting the OpenAI agent needs, and where it comes from.

    This is the single place that knows about OPENAI_API_KEY/OPENAI_MODEL -
    no other module should read those env vars directly.
    """

    api_key: Optional[str] = None
    model: Optional[str] = None

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        return cls(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_MODEL"))


class OpenAIAgent(Agent):
    """OpenAI agent using the current (>=1.0) `openai` SDK's client-object API.

    Ported from the pre-1.0 `openai.ChatCompletion.create(...)` module-level
    call style during the crawl4ai migration - installing crawl4ai transitively
    upgraded the `openai` package (1.0.0 -> 2.53.0+ in this venv), which
    removed `openai.ChatCompletion`/module-level `openai.api_key` entirely.
    Not a design change, just following the SDK's own client-instance model.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize OpenAI agent with API key and model, falling back to OpenAIConfig.from_env()."""
        config = OpenAIConfig.from_env()
        self._client = OpenAI(api_key=api_key or config.api_key)
        self.model = model or config.model or "gpt-3.5-turbo"

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate response using the OpenAI chat completions API."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1200,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
