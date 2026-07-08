"""
Gemini agent implementation for Pragma.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

from ..core.interfaces import Agent


def _find_text_in_common_fields(j: dict[str, Any]) -> str:
    """Scan common top-level fields for text."""
    for key in ("candidates", "outputs", "output", "result", "response"):
        if key in j:
            val = j[key]
            if isinstance(val, list) and val:
                return _extract_text_from_json(val[0])
            return _extract_text_from_json(val)
    return ""


def _extract_text_from_json(j: Any) -> str:
    """Heuristic to walk JSON and return the first string found."""
    if isinstance(j, str):
        return j
    if isinstance(j, dict):
        text = _find_text_in_common_fields(j)
        if text:
            return text
        for val in j.values():
            text = _extract_text_from_json(val)
            if text:
                return text
    if isinstance(j, list):
        for item in j:
            text = _extract_text_from_json(item)
            if text:
                return text
    return ""


class GeminiAgent(Agent):
    """Gemini agent supporting API-key and OAuth flows."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize Gemini agent with API key and model."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("No Gemini API key found in environment")
        
        # Ensure model has 'models/' prefix if not present
        raw_model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
        self.model = raw_model if raw_model.startswith("models/") else f"models/{raw_model}"

        # (version, method_name, use_header_key)
        self._attempts = [
            ("v1beta", "generateContent", True),
            ("v1", "generateContent", True),
        ]

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate content using the best available Gemini endpoint."""
        last_exc: Optional[Exception] = None
        
        for base, method, use_header in self._attempts:
            try:
                return self._try_generate(base, method, use_header, prompt, system_instruction)
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code
                # Stop on auth errors or bad requests (unless it's a 404 which might mean wrong version)
                if status in (401, 403) or (status == 400 and "system_instruction" not in exc.response.text):
                    raise RuntimeError(f"Gemini API Error ({status}): {exc.response.text}") from exc
                
                if status == 404 and base == "v1beta":
                    last_exc = exc
                    continue # Try v1
                
                raise RuntimeError(f"Gemini API Error ({status}): {exc.response.text}") from exc
            except Exception as exc:
                last_exc = exc
                continue

        raise RuntimeError(f"Gemini API failed. Last error: {last_exc}")

    def _try_generate(
        self, base: str, method: str, use_header: bool, prompt: str, system_instruction: Optional[str]
    ) -> str:
        """Attempt a single API request."""
        url = self._build_url(base, method, not use_header)
        headers = {"Content-Type": "application/json"}
        if use_header:
            headers["X-goog-api-key"] = self.api_key

        payload = self._build_payload(method, prompt, system_instruction)
        resp = requests.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code == 400 and system_instruction and "system_instruction" in resp.text:
            return self._retry_without_system_field(url, headers, prompt, system_instruction)

        resp.raise_for_status()
        text = _extract_text_from_json(resp.json())
        return text.strip() if text else str(resp.json())

    def _build_url(self, version: str, method: str, include_key: bool) -> str:
        """Construct the Gemini API URL."""
        base_url = f"https://generativelanguage.googleapis.com/{version}/{self.model}:{method}"
        if include_key:
            return f"{base_url}?key={self.api_key}"
        return base_url

    def _build_payload(
        self, method: str, prompt: str, system_instruction: Optional[str]
    ) -> dict[str, Any]:
        """Build request payload based on method."""
        if method == "generateContent":
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            if system_instruction:
                payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
            return payload

        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        return {"prompt": {"text": full_prompt}, "maxOutputTokens": 800}

    def _retry_without_system_field(
        self, url: str, headers: dict[str, str], prompt: str, system_instruction: str
    ) -> str:
        """Fallback for models not supporting system_instruction field."""
        fallback_prompt = f"SYSTEM INSTRUCTION:\n{system_instruction}\n\nUSER PROMPT:\n{prompt}"
        payload = {"contents": [{"parts": [{"text": fallback_prompt}]}]}
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        text = _extract_text_from_json(resp.json())
        return text.strip() if text else str(resp.json())
