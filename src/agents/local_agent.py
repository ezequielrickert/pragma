"""
Local agent implementation for Pragma, connecting to a local model API.
"""
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

    This is the single place that knows about LOCAL_API_URL/LOCAL_MODEL/
    LOCAL_API_KEY/LOCAL_MAX_TOKENS - no other module should read those env
    vars directly.
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
            # Only needed when the server isn't a bare localhost/LAN endpoint -
            # e.g. an LM Studio instance exposed through a Tailscale tunnel,
            # which fronts it with bearer-token auth (see LocalAgent._headers).
            api_key=os.getenv("LOCAL_API_KEY"),
            # Unset by default (unlike OpenAIAgent's hardcoded max_tokens=1200) -
            # a local reasoning model (DeepSeek-R1 and similar) can legitimately
            # need many tokens of chain-of-thought before it reaches its actual
            # answer, and guessing a "safe" default risks silently truncating
            # that mid-thought. Opt in explicitly once you know your model's
            # real budget (see this class's docstring).
            max_tokens=int(env_max_tokens) if env_max_tokens else None,
        )


@AGENT_REGISTRY.register("local")
class LocalAgent(Agent):
    """Agent that communicates with a local model API (e.g., LM Studio).

    Post-crawl4ai-migration: this is plain text-completion only - the native
    OpenAI-style tool-calling ladder (`act()`/`_act_native`/`_parse_tool_call`)
    that used to live here existed solely to fill a per-step structured action
    schema, which no longer exists (see `src/core/interfaces.py`'s docstring).
    `generate()` is used by the fill-value (Phase 4) and synthesis (Phase 5)
    call sites, both plain text completions.
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
        # Optional bearer token - LM Studio itself doesn't need one on a bare
        # LAN/localhost endpoint, but a server fronted by a tunnel (e.g.
        # Tailscale Funnel/Serve) commonly requires `Authorization: Bearer ...`.
        self.api_key = api_key or config.api_key
        # Unset (None) by default - see LocalConfig.max_tokens's docstring for
        # why this isn't defaulted the way OpenAIAgent's is. Only added to a
        # request payload when actually set (see _build_payload).
        self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens

    def _headers(self) -> dict[str, str]:
        """Request headers, including bearer auth when an api_key is configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _raise_if_truncated(choice: dict[str, Any]) -> None:
        """Raise a clear, actionable error if the server cut the response off
        for running out of `max_tokens`, rather than let it masquerade as
        something else downstream.

        `finish_reason == "length"` is the OpenAI-compatible signal for this -
        present regardless of whether the server separates a reasoning model's
        chain-of-thought into its own `reasoning_content` field or leaves it
        inline in `content`. Without this check, a reasoning model (DeepSeek-R1
        and similar) that spends its entire `max_tokens` budget "thinking"
        returns an empty `content` - which looks, from every other code path's
        point of view, like an ordinary malformed response, silently giving no
        indication the actual cause was one fixed, config-level number.
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
