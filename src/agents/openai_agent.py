"""
OpenAI agent implementation for Pragma.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import openai

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
    """OpenAI agent utilizing ChatCompletion API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize OpenAI agent with API key and model, falling back to OpenAIConfig.from_env()."""
        config = OpenAIConfig.from_env()
        key = api_key or config.api_key
        if key:
            openai.api_key = key
        self.model = model or config.model or "gpt-3.5-turbo"

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate response using OpenAI ChatCompletion."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        resp = openai.ChatCompletion.create(
            model=self.model,
            messages=messages,
            max_tokens=1200,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
