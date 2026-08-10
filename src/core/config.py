"""Layered configuration: defaults < env vars < YAML file < explicit CLI flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

import yaml


@dataclass
class PragmaConfig:
    """Wiring configuration for the Engine (which plugins, and crawl-tuning settings).
    Details: docs/dev/core/config.md#pragmaconfig
    """

    url: Optional[str] = None
    agent: str = "openai"
    graph_store: str = "memory"
    out_dir: str = "docs"
    headless: bool = True
    # Settle time before discovery reads a plain navigation.
    # Details: docs/dev/core/config.md#wait_seconds
    wait_seconds: float = 2.0
    # Same purpose, applied after a click/fill's own re-discovery instead.
    # Details: docs/dev/core/config.md#interaction_wait_seconds
    interaction_wait_seconds: Optional[float] = None
    # crawl4ai's raw navigation/goto dead-page timeout, a different phase.
    # Details: docs/dev/core/config.md#page_timeout_seconds
    page_timeout_seconds: float = 15.0
    # A third timeout phase, bounding Playwright's own unbounded internal waits.
    # Details: docs/dev/core/config.md#interaction_timeout_seconds
    interaction_timeout_seconds: Optional[float] = None
    # Skips crawl4ai's own markdown-generation pipeline; empties debug snapshots.
    # Details: docs/dev/core/config.md#prefetch
    prefetch: bool = False
    # Aborts image/media/font network requests outright; a real behavior change.
    # Details: docs/dev/core/config.md#block_images
    block_images: bool = False
    # Per-page interaction cap, a backstop not a normal-case limiter.
    # Details: docs/dev/core/config.md#element_budget
    element_budget: int = 200
    # Total pages before stopping; None = unbounded.
    # Details: docs/dev/core/config.md#max_pages
    max_pages: Optional[int] = None
    # Max revisits to drain one page's interaction frontier.
    # Details: docs/dev/core/config.md#max_passes_per_page
    max_passes_per_page: int = 10
    # Pages per GraphPRDSynthesizer batch-summarize call.
    # Details: docs/dev/core/config.md#prd_synth_batch_size
    prd_synth_batch_size: int = 5
    # Backstop against a site minting a fresh per-visit-token URL.
    # Details: docs/dev/core/config.md#max_visits_per_route_shape
    max_visits_per_route_shape: int = 1
    # Whether MechanicalCrawler asks `agent` for a realistic fill value.
    # Details: docs/dev/core/config.md#ai_fill_values
    ai_fill_values: bool = True
    # How many pages MechanicalCrawler.crawl_site visits concurrently.
    # Details: docs/dev/core/config.md#page_concurrency
    page_concurrency: int = 1
    # Whether a subdomain counts as in-scope for MechanicalCrawler's frontier.
    # Details: docs/dev/core/config.md#allow_subdomains
    allow_subdomains: bool = False
    # Purge this site's previous graph_store state before crawling.
    # Details: docs/dev/core/config.md#fresh
    fresh: bool = True
    # Where per-run debug artifacts go; "" disables debug logging entirely.
    # Details: docs/dev/core/config.md#debug_logs_dir
    debug_logs_dir: str = "debug_logs"
    # Max past debug_logs_dir run directories to keep for this site+URL.
    # Details: docs/dev/core/config.md#debug_logs_keep_last
    debug_logs_keep_last: Optional[int] = None
    # Also write the full crawl graph as structured JSON.
    # Details: docs/dev/core/config.md#export_json
    export_json: bool = False
    # Component-tree rendering mode: Unicode box-drawing by default.
    # Details: docs/dev/core/config.md#tree_ascii
    tree_ascii: bool = False
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    graph_stores: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    _ENV_MAP: ClassVar[Dict[str, str]] = {
        "url": "URL",
        "agent": "AGENT_PROVIDER",
    }

    def _apply_env(self) -> None:
        for field_name, env_name in self._ENV_MAP.items():
            val = os.getenv(env_name)
            if val:
                setattr(self, field_name, val)

    def _apply_yaml(self, yaml_path: Optional[str]) -> None:
        path = Path(yaml_path) if yaml_path else Path("pragma.yaml")
        if not path.exists():
            if yaml_path:
                raise FileNotFoundError(f"Config file not found: {yaml_path}")
            return

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        valid = {f.name for f in fields(self)}
        for key, val in data.items():
            if key in valid and val is not None:
                setattr(self, key, val)
        print(f"Loaded config from {path}")

    def _apply_overrides(self, overrides: Optional[Dict[str, Any]]) -> None:
        for key, val in (overrides or {}).items():
            if val is not None:
                setattr(self, key, val)

    @classmethod
    def load(
        cls, cli_overrides: Optional[Dict[str, Any]] = None, yaml_path: Optional[str] = None
    ) -> "PragmaConfig":
        """Merge env vars, an optional YAML file, and CLI flags into a PragmaConfig.
        Details: docs/dev/core/config.md#load
        """
        cfg = cls()
        cfg._apply_env()
        cfg._apply_yaml(yaml_path)
        cfg._apply_overrides(cli_overrides)
        return cfg
