import os
from typing import Optional
from ..interfaces import Agent

try:
    import openai
except Exception:
    openai = None

class OpenAIAgent(Agent):
    def __init__(self, api_key: Optional[str] = None, model: str = None):
        api_key = api_key or os.getenv('OPENAI_API_KEY')
        if api_key and openai:
            openai.api_key = api_key
        self.model = model or os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

    def generate(self, prompt: str) -> str:
        if openai is None:
            raise RuntimeError('openai package is not installed')
        resp = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
