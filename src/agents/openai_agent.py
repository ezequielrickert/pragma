"""
OpenAI agent implementation for Pragma.
"""
from __future__ import annotations

import os
from typing import Optional

import openai

from ..interfaces import Agent


class OpenAIAgent(Agent):
    """OpenAI agent utilizing ChatCompletion API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize OpenAI agent with API key and model."""
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key:
            openai.api_key = key
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

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
