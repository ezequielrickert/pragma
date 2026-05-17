"""
Local agent implementation for Pragma, connecting to a local model API.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

from ..interfaces import Agent


class LocalAgent(Agent):
    """Agent that communicates with a local model API (e.g., LM Studio)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        """Initialize LocalAgent."""
        self.base_url = (
            base_url
            or os.getenv("LOCAL_API_URL")
            or "http://192.168.68.76:1234/v1/chat/completions"
        )
        self.model = model or os.getenv("LOCAL_MODEL", "google/gemma-4-e2b")
        self.timeout = timeout

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate content using the local API with fallback for system role."""
        try:
            return self._generate_request(prompt, system_instruction)
        except RuntimeError as exc:
            if "Local API Error (400)" in str(exc) and system_instruction:
                # Fallback: Merge system instruction into user prompt
                fallback_prompt = f"SYSTEM:\n{system_instruction}\n\nUSER:\n{prompt}"
                return self._generate_request(fallback_prompt, None)
            raise

    def _generate_request(self, prompt: str, system_instruction: Optional[str]) -> str:
        """Internal helper to make the API request."""
        payload = self._build_payload(prompt, system_instruction)

        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Local API Error ({resp.status_code}): {resp.text}")
            return self._parse_response(resp.json())

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Local API request failed: {exc}") from exc

    def _build_payload(self, prompt: str, system_instruction: Optional[str]) -> dict[str, Any]:
        """Build the OpenAI-compatible request payload."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }

    def _parse_response(self, data: dict[str, Any]) -> str:
        """Extract content from OpenAI-compatible response format."""
        try:
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError(f"Unexpected API response format: {data}")
                
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Failed to parse Local API response: {exc}") from exc
