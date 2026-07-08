"""Registered builders for agents whose construction needs env-based logic."""
from __future__ import annotations

import os

from ..core.interfaces import Agent
from ..core.registry import AGENT_REGISTRY

try:
    from .gemini_agent import GeminiAgent
except ImportError:
    GeminiAgent = None

try:
    from .gemini_oauth_agent import GeminiOAuthAgent
except ImportError:
    GeminiOAuthAgent = None

try:
    from .openai_agent import OpenAIAgent
except ImportError:
    OpenAIAgent = None


@AGENT_REGISTRY.register("gemini")
def build_gemini_agent() -> Agent:
    """Instantiate Gemini agent with appropriate auth."""
    model = os.getenv("GEMINI_MODEL")
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if creds:
        if GeminiOAuthAgent is None:
            raise ImportError("google-auth package is required for OAuth")
        return GeminiOAuthAgent(creds_file=creds, model=model)

    if GeminiAgent is None:
        raise ImportError("requests package is required for GeminiAgent")

    key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    return GeminiAgent(api_key=key, model=model)


@AGENT_REGISTRY.register("openai")
def build_openai_agent() -> Agent:
    """Instantiate OpenAI agent if key and package are present."""
    if OpenAIAgent is None:
        raise ImportError("openai package is required for OpenAIAgent")

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not found")
    return OpenAIAgent()
