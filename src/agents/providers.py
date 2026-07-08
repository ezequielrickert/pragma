"""Registered builders for agents whose construction needs env-based logic.

Each provider owns its config (a dataclass colocated with its Agent implementation,
e.g. GeminiConfig in gemini_agent.py). These builders only decide *which* concrete
class to instantiate and forward any explicit overrides (e.g. from pragma.yaml's
`agents:` block) on top of that provider's own env-derived defaults.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from ..core.interfaces import Agent
from ..core.registry import AGENT_REGISTRY

try:
    from .gemini_agent import GeminiAgent, GeminiConfig
except ImportError:
    GeminiAgent = None
    GeminiConfig = None

try:
    from .gemini_oauth_agent import GeminiOAuthAgent, GeminiOAuthConfig
except ImportError:
    GeminiOAuthAgent = None
    GeminiOAuthConfig = None

try:
    from .openai_agent import OpenAIAgent, OpenAIConfig
except ImportError:
    OpenAIAgent = None
    OpenAIConfig = None


def _apply_overrides(config: Any, overrides: Dict[str, Any]) -> Any:
    """Apply explicit overrides (e.g. from pragma.yaml) on top of a Config.from_env()."""
    for key, value in overrides.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    return config


@AGENT_REGISTRY.register("gemini")
def build_gemini_agent(**overrides: Any) -> Agent:
    """Instantiate Gemini agent with appropriate auth.

    Uses OAuth (service account) if a credentials file is configured, otherwise
    falls back to the API-key REST flow.
    """
    creds_file = overrides.get("creds_file") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_file:
        if GeminiOAuthAgent is None:
            raise ImportError("google-auth package is required for OAuth")
        config = _apply_overrides(GeminiOAuthConfig.from_env(), overrides)
        return GeminiOAuthAgent(creds_file=creds_file, model=config.model)

    if GeminiAgent is None:
        raise ImportError("requests package is required for GeminiAgent")

    config = _apply_overrides(GeminiConfig.from_env(), overrides)
    return GeminiAgent(api_key=config.api_key, model=config.model)


@AGENT_REGISTRY.register("openai")
def build_openai_agent(**overrides: Any) -> Agent:
    """Instantiate OpenAI agent if key and package are present."""
    if OpenAIAgent is None:
        raise ImportError("openai package is required for OpenAIAgent")

    config = _apply_overrides(OpenAIConfig.from_env(), overrides)
    if not config.api_key:
        raise ValueError("OPENAI_API_KEY not found")
    return OpenAIAgent(api_key=config.api_key, model=config.model)
