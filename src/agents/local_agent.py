"""
Local agent implementation for Pragma, connecting to a local model API.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from ..core.interfaces import HELP_TOPICS, TOOL_SPECS, Agent, AgentAction, parse_agent_action
from ..core.registry import AGENT_REGISTRY


@dataclass
class LocalConfig:
    """Every setting the local agent needs, and where it comes from.

    This is the single place that knows about LOCAL_API_URL/LOCAL_MODEL/
    LOCAL_API_KEY - no other module should read those env vars directly.
    """

    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 300
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LocalConfig":
        env_timeout = os.getenv("LOCAL_TIMEOUT")
        return cls(
            base_url=os.getenv("LOCAL_API_URL"),
            model=os.getenv("LOCAL_MODEL"),
            timeout=int(env_timeout) if env_timeout else 300,
            # Only needed when the server isn't a bare localhost/LAN endpoint -
            # e.g. an LM Studio instance exposed through a Tailscale tunnel,
            # which fronts it with bearer-token auth (see LocalAgent._headers).
            api_key=os.getenv("LOCAL_API_KEY"),
        )


@AGENT_REGISTRY.register("local")
class LocalAgent(Agent):
    """Agent that communicates with a local model API (e.g., LM Studio)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        api_key: Optional[str] = None,
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
        # None = not yet tried; True/False cached after the first act() call, so a
        # server/model that doesn't support the `tools` param only pays for one
        # failed round trip per run, not one per iteration.
        self._tools_supported: Optional[bool] = None

    def _headers(self) -> dict[str, str]:
        """Request headers, including bearer auth when an api_key is configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def act(
        self,
        prompt: str,
        tools: List[Dict[str, Any]] = TOOL_SPECS,
        system_instruction: Optional[str] = None,
    ) -> AgentAction:
        """Prefer native OpenAI-style function-calling; fall back to the text protocol.

        Many OpenAI-compatible local servers (LM Studio included) accept a
        `tools` request param, but whether the loaded model actually honors it
        (returns `tool_calls` instead of plain text) depends on the model's
        chat template - some GGUF Gemma builds simply ignore it. Rather than
        assume either way, try once, and remember the outcome for this
        instance's lifetime (see `_tools_supported`).
        """
        if self._tools_supported is not False:
            try:
                action = self._act_native(prompt, tools, system_instruction)
            except RuntimeError:
                action = None
            if action is not None:
                self._tools_supported = True
                return action
            self._tools_supported = False
        return super().act(prompt, tools, system_instruction)

    def _act_native(
        self, prompt: str, tools: List[Dict[str, Any]], system_instruction: Optional[str]
    ) -> Optional[AgentAction]:
        """Attempt one native tool-calling request. Returns None if the server/model didn't cooperate."""
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "tools": [self._to_openai_tool(tool) for tool in tools],
            "tool_choice": "required",
        }
        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Local API request failed: {exc}") from exc
        if resp.status_code != 200:
            # Server rejected the `tools` param outright - not supported, fall back.
            return None
        try:
            message = resp.json()["choices"][0]["message"]
        except (KeyError, IndexError, ValueError):
            return None
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            # Request was accepted but the model replied with plain text instead
            # of a tool call - its chat template doesn't actually support this.
            return None
        return self._parse_tool_call(tool_calls[0])

    @staticmethod
    def _parse_tool_call(tool_call: dict[str, Any]) -> Optional[AgentAction]:
        """Turn one OpenAI-style `tool_calls[i]` entry into an AgentAction, or None if malformed."""
        function = tool_call.get("function", {})
        name = {"goto": "navigate"}.get(function.get("name", ""), function.get("name", ""))
        if name not in ("navigate", "click", "fill", "submit", "finish"):
            return None
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        ref = args.get("ref")
        try:
            ref = int(ref) if ref is not None else None
        except (TypeError, ValueError):
            ref = None
        # `raw` includes `name` (unlike `args` itself) purely so progress logs are
        # self-describing - `Action: {"ref": 1}` alone doesn't say whether that was a
        # click or a fill, which made a native-tool-calling model silently omitting
        # `value` on a fill (see SimplePRDGenerator._execute_action's fallback for why
        # that matters) much harder to spot in `progress_log_file` than it needed to be.
        return AgentAction(
            kind=name, ref=ref, url=args.get("url"), value=args.get("value"),
            raw=json.dumps({"action": name, **args}),
        )

    @staticmethod
    def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Convert a Pragma tool spec (see TOOL_SPECS) into an OpenAI `tools` function entry.

        `help`'s `topic` gets a real JSON-schema `enum`, not just prose in its
        `description` - a model hallucinated "navigation" (not a real topic;
        `navigate_usage` is) despite the valid list being spelled out in that
        description string. A structural `enum` is a stronger signal than
        prose for any model/server that actually honors JSON schema during
        tool-call generation, and is strictly more correct regardless.
        """
        properties = {
            name: {"type": "integer" if name == "ref" else "string", "description": desc}
            for name, desc in tool["parameters"].items()
        }
        if tool["name"] == "help" and "topic" in properties:
            properties["topic"]["enum"] = HELP_TOPICS
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties.keys()),
                },
            },
        }

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
