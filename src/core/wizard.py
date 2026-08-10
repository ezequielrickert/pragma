"""Interactive setup wizard: configure Pragma's wiring once, then just run it.
Details: docs/dev/core/wizard.md#module
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from dotenv import dotenv_values

from ..utils.io import upsert_env_vars
from . import prompts
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY

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
        {
            "name": "timeout",
            "label": "Request timeout in seconds (raise this if generation times out)",
            "default": "300",
            "secret": False,
            "type": "int",
        },
        {
            "name": "api_key",
            "label": "Bearer token (blank = keep current / none needed for a bare local endpoint)",
            "secret": True,
            "env": "LOCAL_API_KEY",
        },
    ],
    "mock": [],
}

# Per-graph-store prompts, same shape as PROVIDER_FIELDS - persisted to
# pragma.yaml's `graph_stores:` block (non-secret) / .env (secret).
GRAPH_STORE_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "neo4j": [
        {"name": "host", "label": "Neo4j host", "default": "localhost", "secret": False},
        {
            "name": "port",
            "label": "Neo4j bolt port",
            "default": "7687",
            "secret": False,
            "type": "int",
        },
        {"name": "database", "label": "Neo4j database name", "default": "neo4j", "secret": False},
        {"name": "user", "label": "Neo4j username", "default": "neo4j", "secret": False},
        {
            "name": "password",
            "label": "Neo4j password (blank = keep current)",
            "secret": True,
            "env": "NEO4J_PASSWORD",
        },
    ],
    "memory": [],
}


def _load_existing_yaml() -> Dict[str, Any]:
    path = Path(PRAGMA_YAML)
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _prompt_secret_field(field: Dict[str, Any], env_values: Dict[str, Any]) -> Optional[str]:
    label = field["label"]
    if env_values.get(field["env"]):
        label += " [already set]"
    return prompts.secret(label) or None


def _prompt_text_field(field: Dict[str, Any], current: Dict[str, Any]) -> Any:
    default = str(current.get(field["name"], field["default"]))
    value = prompts.text(field["label"], default=default)
    if not value:
        return None
    if field.get("type") == "int" and value.isdigit():
        return int(value)
    return value


def _prompt_provider_fields(
    provider: str,
    existing_overrides: Dict[str, Any],
    env_values: Dict[str, Any],
    fields_table: Dict[str, List[Dict[str, Any]]] = PROVIDER_FIELDS,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Prompt for every field a provider needs; returns (yaml overrides, env secrets).
    Details: docs/dev/core/wizard.md#_prompt_provider_fields
    """
    provider_overrides = dict(existing_overrides)
    secrets_to_write: Dict[str, str] = {}

    for field in fields_table.get(provider, []):
        if field["secret"]:
            value = _prompt_secret_field(field, env_values)
            if value:
                secrets_to_write[field["env"]] = value
            # Blank means "keep whatever is already in .env" - never overwrite with "".
        else:
            value = _prompt_text_field(field, provider_overrides)
            if value is not None:
                provider_overrides[field["name"]] = value

    return provider_overrides, secrets_to_write


def _prompt_pipeline_settings(existing: Dict[str, Any]) -> Dict[str, Any]:
    headless = prompts.confirm("Run browser headless?", default=existing.get("headless", True))
    wait_seconds_raw = prompts.text(
        "Seconds to let a page settle before discovery reads it (raise for JS-heavy/SPA sites, "
        "where the default can otherwise see 0 components/links on a page that has real ones)",
        default=str(existing.get("wait_seconds", 2)),
    )
    element_budget_raw = prompts.text(
        "Max components mechanically interacted with per page per visit-pass "
        "(the backstop against a pathological reveal-chain, not a normal-case limit)",
        default=str(existing.get("element_budget", 200)),
    )
    max_pages_raw = prompts.text(
        "Max pages to visit per crawl (blank = unbounded, crawl until the URL frontier is exhausted)",
        default=str(existing.get("max_pages", "")),
    )
    max_passes_per_page_raw = prompts.text(
        "Max times to revisit the same page to keep draining its interaction frontier "
        "(a page with more components than the element budget needs more than one pass)",
        default=str(existing.get("max_passes_per_page", 10)),
    )
    tree_ascii = prompts.confirm(
        "Render the component-tree document with plain ASCII instead of Unicode box-drawing "
        "characters? (for terminals that mangle Unicode)",
        default=existing.get("tree_ascii", False),
    )
    return {
        "out_dir": prompts.text("Output folder for PRDs", default=existing.get("out_dir", "docs")),
        "headless": bool(headless),
        "wait_seconds": float(wait_seconds_raw) if _is_number(wait_seconds_raw) else 2.0,
        "element_budget": int(element_budget_raw) if element_budget_raw.isdigit() else 200,
        "max_pages": int(max_pages_raw) if max_pages_raw.isdigit() else None,
        "max_passes_per_page": int(max_passes_per_page_raw) if max_passes_per_page_raw.isdigit() else 10,
        "tree_ascii": bool(tree_ascii),
    }


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def run_config_wizard() -> None:
    """Interactively configure agent/graph-store wiring and persist it."""
    existing = _load_existing_yaml()
    existing_agents = existing.get("agents", {})
    existing_graph_stores = existing.get("graph_stores", {})
    env_values = dotenv_values(ENV_FILE) if Path(ENV_FILE).exists() else {}

    print("Pragma setup - configure once, then just run: python3 src/cli.py <url>\n")

    agent = prompts.select(
        "Agent / model provider:", AGENT_REGISTRY.names(), default=existing.get("agent")
    )
    graph_store = prompts.select(
        "Graph store (where the navigation graph is tracked/queried):",
        GRAPH_STORE_REGISTRY.names(),
        default=existing.get("graph_store", "memory"),
    )

    provider_overrides, secrets_to_write = _prompt_provider_fields(
        agent, existing_agents.get(agent, {}), env_values
    )
    graph_store_overrides, graph_store_secrets = _prompt_provider_fields(
        graph_store, existing_graph_stores.get(graph_store, {}), env_values, GRAPH_STORE_FIELDS
    )
    secrets_to_write.update(graph_store_secrets)
    pipeline_settings = _prompt_pipeline_settings(existing)

    config_data: Dict[str, Any] = {
        "agent": agent,
        "graph_store": graph_store,
        **pipeline_settings,
    }
    all_agents = dict(existing_agents)
    if provider_overrides:
        all_agents[agent] = provider_overrides
    if all_agents:
        config_data["agents"] = all_agents

    all_graph_stores = dict(existing_graph_stores)
    if graph_store_overrides:
        all_graph_stores[graph_store] = graph_store_overrides
    if all_graph_stores:
        config_data["graph_stores"] = all_graph_stores

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
