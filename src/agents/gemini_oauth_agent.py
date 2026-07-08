"""
Gemini agent using Google service account OAuth tokens.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from ..core.interfaces import Agent


class GeminiOAuthAgent(Agent):
    """Gemini agent using Google service account OAuth tokens."""

    def __init__(self, creds_file: Optional[str] = None, model: Optional[str] = None) -> None:
        """Initialize with service account credentials."""
        path = creds_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not path:
            raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS must be set")
        
        self.creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.model = model or os.getenv("GEMINI_MODEL", "models/text-bison-001")
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta2/{self.model}:generateText"
        )

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generate text using authenticated service account."""
        self._refresh_creds()
        
        headers = {
            "Authorization": f"Bearer {self.creds.token}",
            "Content-Type": "application/json",
        }
        
        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        payload = {
            "prompt": {"text": full_prompt},
            "maxOutputTokens": 800,
        }
        
        resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return self._parse_response(resp.json())

    def _refresh_creds(self) -> None:
        """Refresh OAuth token if needed."""
        try:
            self.creds.refresh(Request())
        except Exception as exc:
            raise RuntimeError(f"Failed to refresh service account token: {exc}") from exc

    def _parse_response(self, j: Any) -> str:
        """Extract text from the response JSON."""
        if not isinstance(j, dict):
            return ""
            
        candidates = j.get("candidates")
        if candidates and isinstance(candidates, list) and candidates:
            first = candidates[0]
            return (first.get("content") or first.get("text") or "").strip()
            
        return (j.get("output") or j.get("result") or "").strip()
