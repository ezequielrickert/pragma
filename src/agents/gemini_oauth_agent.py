import os
from typing import Optional

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from ..interfaces import Agent

class GeminiOAuthAgent(Agent):
    """Gemini agent using Google service account OAuth tokens.

    Expects GOOGLE_APPLICATION_CREDENTIALS to point to a service account JSON file
    with permissions to call the Generative Language API (Vertex AI / Generative Language).
    """

    def __init__(self, creds_file: Optional[str] = None, model: Optional[str] = None):
        creds_file = creds_file or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_file:
            raise RuntimeError('GOOGLE_APPLICATION_CREDENTIALS must be set for GeminiOAuthAgent')
        self.creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        self.model = model or os.getenv('GEMINI_MODEL', 'models/text-bison-001')
        self.endpoint = f'https://generativelanguage.googleapis.com/v1beta2/{self.model}:generateText'

    def generate(self, prompt: str) -> str:
        # refresh token if needed
        try:
            self.creds.refresh(Request())
        except Exception as e:
            raise RuntimeError(f'Failed to refresh service account token: {e}')
        token = self.creds.token
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'prompt': {'text': prompt},
            'maxOutputTokens': 800,
        }
        resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        j = resp.json()
        # Parse common response shapes
        content = ''
        if isinstance(j, dict):
            candidates = j.get('candidates')
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                content = candidates[0].get('content') or candidates[0].get('text') or ''
            if not content:
                content = j.get('output') or j.get('result') or ''
        return (content or '').strip()
