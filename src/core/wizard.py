"""Interactive setup wizard: configure Pragma's wiring once, then just run it.

Non-secret settings (which plugins, model names, endpoints) are written to
`pragma.yaml`. Secrets (API keys) are written to `.env`. Existing values are
shown as editable defaults, so re-running the wizard is a safe way to tweak
a single setting without hand-editing YAML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import dotenv_values

from ..utils.io import upsert_env_vars
from . import prompts
from .registry import AGENT_REGISTRY, GENERATOR_REGISTRY, SCRAPER_REGISTRY

PRAGMA_YAML = "pragma.yaml"
ENV_FILE = ".env"

# Per-provider prompts. Non-secret fields are persisted to pragma.yaml's `agents:`
# block; secret fields are persisted to .env under their own env var name.
PROVIDER_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "gemini": [
        {
            "name": "model",
            "label": "Gemini model",
            "default": "models/gemini-1.5-flash-latest",
            "secret": False,
        },
        {
            "name": "api_key",
            "label": "Gemini API key (blank = keep current / use OAuth instead)",
            "secret": True,
            "env": "GEMINI_API_KEY",
        },
    ],
    "openai": [
        {"name": "model", "label": "OpenAI model", "default": "gpt-3.5-turbo", "secret": False},
        {
            "name": "api_key",
            "label": "OpenAI API key (blank = keep current)",
            "secret": True,
            "env": "OPENAI_API_KEY",
        },
    ],
    "local": [
        {
            "name": "base_url",
            "label": "Local server URL",
            "default": "http://localhost:1234/v1/chat/completions",
            "secret": False,
        },
        {
            "name": "model",
            "label": "Local model name",
            "default": "google/gemma-4-e2b",
            "secret": False,
        },
    ],
    "mock": [],
}


def _load_existing_yaml() -> Dict[str, Any]:
    path = Path(PRAGMA_YAML)
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def run_config_wizard() -> None:
    """Interactively configure scraper/agent/generator wiring and persist it."""
    existing = _load_existing_yaml()
    existing_agents = existing.get("agents", {})
    env_values = dotenv_values(ENV_FILE) if Path(ENV_FILE).exists() else {}

    print("Pragma setup - configure once, then just run: python3 src/cli.py <url>\n")

    scraper = prompts.select(
        "Scraper plugin:", SCRAPER_REGISTRY.names(), default=existing.get("scraper", "playwright")
    )
    agent = prompts.select(
        "Agent / model provider:", AGENT_REGISTRY.names(), default=existing.get("agent")
    )
    generator = prompts.select(
        "Generator strategy:", GENERATOR_REGISTRY.names(), default=existing.get("generator", "simple")
    )

    provider_overrides: Dict[str, Any] = dict(existing_agents.get(agent, {}))
    secrets_to_write: Dict[str, str] = {}

    for field in PROVIDER_FIELDS.get(agent, []):
        if field["secret"]:
            label = field["label"]
            if env_values.get(field["env"]):
                label += " [already set]"
            value = prompts.secret(label)
            if value:
                secrets_to_write[field["env"]] = value
            # Blank means "keep whatever is already in .env" - never overwrite with "".
        else:
            current_default = provider_overrides.get(field["name"], field["default"])
            value = prompts.text(field["label"], default=current_default)
            if value:
                provider_overrides[field["name"]] = value

    headless = prompts.confirm("Run browser headless?", default=existing.get("headless", True))
    max_iterations_raw = prompts.text(
        "Max iterations per run", default=str(existing.get("max_iterations", 12))
    )
    out_dir = prompts.text("Output folder for PRDs", default=existing.get("out_dir", "docs"))
    logs_dir = prompts.text(
        "Folder for research logs", default=existing.get("logs_dir", "research_logs")
    )

    config_data: Dict[str, Any] = {
        "scraper": scraper,
        "agent": agent,
        "generator": generator,
        "out_dir": out_dir,
        "logs_dir": logs_dir,
        "headless": bool(headless),
        "max_iterations": int(max_iterations_raw) if max_iterations_raw.isdigit() else 12,
    }
    all_agents = dict(existing_agents)
    if provider_overrides:
        all_agents[agent] = provider_overrides
    if all_agents:
        config_data["agents"] = all_agents

    Path(PRAGMA_YAML).write_text(
        "# Written by `python3 src/cli.py config`. Edit freely or re-run the wizard.\n"
        + yaml.safe_dump(config_data, sort_keys=False),
        encoding="utf-8",
    )
    print(f"\nSaved wiring to {PRAGMA_YAML}")

    if secrets_to_write:
        upsert_env_vars(ENV_FILE, secrets_to_write)
        print(f"Saved secret(s) to {ENV_FILE}: {', '.join(secrets_to_write)}")

    print("\nDone. Run `python3 src/cli.py <url>` to start an analysis.")
