"""
Factory for creating Agent instances.
"""
from __future__ import annotations

import os
from typing import Optional

from ..interfaces import Agent
from .mock_agent import MockAgent
from .local_agent import LocalAgent

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


class AgentFactory:
    """Factory to instantiate Agent based on provider and environment."""

    @staticmethod
    def create_agent(provider: Optional[str] = None) -> Agent:
        """Create an Agent instance.

        Args:
            provider: The LLM provider (gemini, openai, mock).

        Returns:
            An implementation of the Agent interface.
        """
        provider = provider or os.getenv("AGENT_PROVIDER", "openai").lower()

        try:
            if provider == "gemini":
                return AgentFactory._create_gemini_agent()
            if provider == "openai":
                return AgentFactory._create_openai_agent()
            if provider == "local":
                return LocalAgent()
            if provider == "mock":
                return MockAgent()
        except Exception as exc:
            print(f"Failed to initialize {provider} agent: {exc}")

        print(f"Falling back to MockAgent (Requested: {provider})")
        return MockAgent()

    @staticmethod
    def _create_gemini_agent() -> Agent:
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

    @staticmethod
    def _create_openai_agent() -> Agent:
        """Instantiate OpenAI agent if key and package are present."""
        if OpenAIAgent is None:
            raise ImportError("openai package is required for OpenAIAgent")
        
        if os.getenv("OPENAI_API_KEY"):
            return OpenAIAgent()
        raise ValueError("OPENAI_API_KEY not found")
