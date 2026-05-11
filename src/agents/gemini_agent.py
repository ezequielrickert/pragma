import os
from typing import Optional, Any

import requests

from ..interfaces import Agent


def _extract_text_from_json(j: Any) -> str:
    """Heuristic: walk the JSON and return the first string-looking text found in common fields."""
    if isinstance(j, str):
        return j
    if isinstance(j, dict):
        # common top-level shapes
        for key in ('candidates', 'outputs', 'output', 'result', 'response'):
            if key in j:
                v = j[key]
                if isinstance(v, list) and len(v) > 0:
                    # look into first item
                    return _extract_text_from_json(v[0])
                return _extract_text_from_json(v)
        # otherwise scan values
        for v in j.values():
            t = _extract_text_from_json(v)
            if t:
                return t
    if isinstance(j, list):
        for item in j:
            t = _extract_text_from_json(item)
            if t:
                return t
    return ''


class GeminiAgent(Agent):
    """Gemini agent trying several request patterns to support API-key and OAuth flows.

    Strategy:
    1. Try v1 generateContent endpoint with header X-goog-api-key (recommended for API keys tied to a project)
    2. Fall back to v1beta2 generateText using key as query param
    3. Fall back to v1 generateText using key as query param

    This allows compatibility with a variety of account setups and model names.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise RuntimeError('No Gemini API key found in GEMINI_API_KEY or OPENAI_API_KEY')
        # model could be e.g. 'models/gemini-flash-latest' or 'models/text-bison-001'
        self.model = model or os.getenv('GEMINI_MODEL', 'models/gemini-flash-latest')

        # Attempt patterns in order
        # Each entry: (base_path, method_name, use_header_key(boolean))
        self._attempts = [
            ('v1', 'generateContent', True),
            ('v1beta', 'generateContent', True),
            ('v1beta2', 'generateText', False),
            ('v1', 'generateText', False),
        ]

    def _build_url(self, base: str, method: str, use_query_key: bool) -> str:
        # e.g. https://generativelanguage.googleapis.com/v1/models/gemini-flash-latest:generateContent
        url = f'https://generativelanguage.googleapis.com/{base}/{self.model}:{method}'
        if use_query_key:
            url = url + f'?key={self.api_key}'
        return url

    def generate(self, prompt: str) -> str:
        last_exc = None
        for base, method, use_header in self._attempts:
            url = self._build_url(base, method, not use_header)
            headers = {'Content-Type': 'application/json'}
            if use_header:
                headers['X-goog-api-key'] = self.api_key
            # Build payload per method
            if method == 'generateContent':
                payload = {
                    'contents': [
                        {
                            'parts': [
                                {'text': prompt}
                            ]
                        }
                    ]
                }
            else:
                payload = {
                    'prompt': {'text': prompt},
                    'maxOutputTokens': 800,
                }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                # If 404, try next pattern
                if resp.status_code == 404:
                    last_exc = RuntimeError(f'404 from {url}')
                    continue
                resp.raise_for_status()
                j = resp.json()
                text = _extract_text_from_json(j)
                if not text:
                    # As a last resort return raw json string
                    return str(j)
                return text.strip()
            except requests.exceptions.HTTPError as he:
                last_exc = he
                # For auth/permission issues, include body for clarity
                body = ''
                try:
                    body = resp.text
                except Exception:
                    body = ''
                raise RuntimeError(f'HTTP {resp.status_code} from {url}: {body}') from he
            except requests.exceptions.RequestException as re:
                last_exc = re
                # network or timeout
                raise RuntimeError(f'Network error contacting Gemini API at {url}: {re}') from re

        if last_exc:
            raise RuntimeError(f'Gemini API failed for all tried endpoints. Please check your GEMINI_MODEL and GEMINI_API_KEY. Last error: {last_exc}')
        return ''
