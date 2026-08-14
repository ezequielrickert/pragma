"""Local agent implementation for Pragma, connecting to a local model API."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

from ..core.interfaces import Agent
from ..core.registry import AGENT_REGISTRY


@dataclass
class LocalConfig:
    """Every setting the local agent needs, and where it comes from.
    Details: docs/dev/agents/local_agent.md#localconfig
    """

    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 300
    api_key: Optional[str] = None
    max_tokens: Optional[int] = None

    @classmethod
    def from_env(cls) -> "LocalConfig":
        env_timeout = os.getenv("LOCAL_TIMEOUT")
        env_max_tokens = os.getenv("LOCAL_MAX_TOKENS")
        return cls(
            base_url=os.getenv("LOCAL_API_URL"),
            model=os.getenv("LOCAL_MODEL"),
            timeout=int(env_timeout) if env_timeout else 300,
            # Only needed for a server fronted by tunnel auth (see _headers).
            api_key=os.getenv("LOCAL_API_KEY"),
            # Unset by default - no hardcoded cap.
            # Details: docs/dev/agents/local_agent.md#max_tokens
            max_tokens=int(env_max_tokens) if env_max_tokens else None,
        )


@AGENT_REGISTRY.register("local")
class LocalAgent(Agent):
    """Agent that communicates with a local model API (e.g., LM Studio).
    Details: docs/dev/agents/local_agent.md#localagent
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        """Initialize LocalAgent, falling back to LocalConfig.from_env()."""
        config = LocalConfig.from_env()
        self.base_url = base_url or config.base_url or "http://192.168.68.76:1234/v1/chat/completions"
        self.model = model or config.model or "google/gemma-4-e2b"
        self.timeout = timeout or config.timeout
        # Optional bearer token, for a server fronted by a tunnel (Tailscale).
        self.api_key = api_key or config.api_key
        # Unset by default - see LocalConfig.max_tokens; added to the
        # payload only when actually set (see _build_payload).
        self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens

    def _headers(self) -> dict[str, str]:
        """Request headers, including bearer auth when an api_key is configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _raise_if_truncated(choice: dict[str, Any]) -> None:
        """Raise a clear error if the server truncated the response at max_tokens.
        Details: docs/dev/agents/local_agent.md#_raise_if_truncated
        """
        if choice.get("finish_reason") != "length":
            return
        raise RuntimeError(
            "Response truncated: the model hit max_tokens before finishing (finish_reason: "
            "'length'). This is almost always max_tokens set too low for a reasoning model's "
            "chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/"
            ".env and try again, or unset it entirely to let the model use as much as it needs."
        )

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate content using the local API with fallback for system role."""
        try:
            return self._generate_request(prompt, system_instruction)
        except RuntimeError as exc:
            if "Local API Error (400)" in str(exc) and system_instruction:
                # Fallback: merge system instruction into the user prompt.
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
                headers=self._headers(),
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

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        return payload

    def _parse_response(self, data: dict[str, Any]) -> str:
        """Extract content from OpenAI-compatible response format."""
        try:
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError(f"Unexpected API response format: {data}")

            self._raise_if_truncated(choices[0])
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Failed to parse Local API response: {exc}") from exc
