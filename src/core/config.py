"""Layered configuration: defaults < env vars < YAML file < explicit CLI flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

import yaml


@dataclass
class PragmaConfig:
    """Wiring configuration for the Engine (which plugins, and pipeline settings).

    `agents` holds optional per-provider settings (model, endpoint, etc.), keyed by
    provider name, e.g. {"gemini": {"model": "..."}}. Secrets should stay in env
    vars / .env; `agents` is meant for non-secret, provider-specific overrides that
    would otherwise clutter a single flat .env as more providers are added. Each
    provider is still free to fall back to its own env vars when a key is omitted
    here - see the Config dataclasses colocated with each Agent implementation.
    """

    url: Optional[str] = None
    scraper: str = "playwright"
    agent: str = "openai"
    generator: str = "simple"
    out_dir: str = "docs"
    logs_dir: str = "research_logs"
    headless: bool = True
    max_iterations: int = 12
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    _ENV_MAP: ClassVar[Dict[str, str]] = {
        "url": "URL",
        "agent": "AGENT_PROVIDER",
    }

    @classmethod
    def load(
        cls, cli_overrides: Optional[Dict[str, Any]] = None, yaml_path: Optional[str] = None
    ) -> "PragmaConfig":
        """Build a PragmaConfig by merging env vars, an optional YAML file, and CLI flags.

        Precedence (highest wins): explicit CLI flag > YAML file value > env var > default.
        """
        cfg = cls()

        for field_name, env_name in cls._ENV_MAP.items():
            val = os.getenv(env_name)
            if val:
                setattr(cfg, field_name, val)

        path = Path(yaml_path) if yaml_path else Path("pragma.yaml")
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            valid = {f.name for f in fields(cls)}
            for key, val in data.items():
                if key in valid and val is not None:
                    setattr(cfg, key, val)
            print(f"Loaded config from {path}")
        elif yaml_path:
            raise FileNotFoundError(f"Config file not found: {yaml_path}")

        for key, val in (cli_overrides or {}).items():
            if val is not None:
                setattr(cfg, key, val)

        return cfg
