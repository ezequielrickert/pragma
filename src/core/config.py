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
    # Settle time before discovery reads a plain navigation. A ceiling, not a
    # flat sleep: _wait_for_new_content returns as soon as the DOM changes.
    # Details: docs/dev/core/config.md#wait_seconds
    wait_seconds: float = 1.0
    # Same purpose, applied after a click/fill's own re-discovery instead.
    # Details: docs/dev/core/config.md#interaction_wait_seconds
    interaction_wait_seconds: Optional[float] = None
    # crawl4ai's raw navigation/goto dead-page timeout, a different phase.
    # Details: docs/dev/core/config.md#page_timeout_seconds
    page_timeout_seconds: float = 15.0
    # A third timeout phase, bounding Playwright's own unbounded internal
    # waits. Left unset, Playwright's own 1s default governs instead - real
    # cost on a page stuck behind e.g. an anti-bot block (3 retry attempts at
    # 1s each). Details: docs/dev/core/config.md#interaction_timeout_seconds
    interaction_timeout_seconds: Optional[float] = 1.0
    # Skips crawl4ai's own markdown-generation pipeline; empties debug snapshots.
    # Details: docs/dev/core/config.md#prefetch
    prefetch: bool = False
    # Aborts image/media/font network requests outright; a real behavior change.
    # Details: docs/dev/core/config.md#block_images
    block_images: bool = True
    # Keeps each page rendered for its whole pass by aborting the navigations
    # its own components trigger; the destination is queued, not chased.
    # Details: docs/dev/core/config.md#suppress_navigation
    suppress_navigation: bool = True
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
    # How many pages MechanicalCrawler.crawl_site visits concurrently. A
    # serial (1) crawl pays every page's settle-wait/interaction cost back to
    # back; raising this is the single biggest wall-clock lever this project
    # has (see docs/dev/crawlers/mechanical_loop.md), paired with
    # MechanicalCrawlerConfig's own memory_ceiling_percent so more workers
    # don't just trade wall-clock time for the same OOM risk.
    # Details: docs/dev/core/config.md#page_concurrency
    page_concurrency: int = 4
    # Real Chromium processes in Crawl4AICrawlerPool. `None` ties it to
    # page_concurrency (one dedicated browser per worker, the default).
    # Set lower to have several workers share each browser process (less
    # memory, less isolation) - never higher than page_concurrency, since a
    # browser with no worker ever routed to it would just sit idle.
    # Details: docs/dev/core/config.md#browser_pool_size
    browser_pool_size: Optional[int] = None
    # Whether a subdomain counts as in-scope for MechanicalCrawler's frontier.
    # Details: docs/dev/core/config.md#allow_subdomains
    allow_subdomains: bool = False
    # Purge this site's previous graph_store state before crawling; false
    # resumes that state's unfinished frontier instead.
    # Details: docs/dev/core/config.md#fresh
    fresh: bool = True
    # Pages this session may visit before stopping so the rest can be
    # resumed later. Unlike max_pages (which bounds the whole crawl, however
    # many sessions it takes), this bounds one sitting.
    # Details: docs/dev/core/config.md#stop_after_pages
    stop_after_pages: Optional[int] = None
    # Wall-clock seconds this session may run before stopping the same way.
    # Details: docs/dev/core/config.md#stop_after_seconds
    stop_after_seconds: Optional[float] = None
    # Consecutive circuit-breaker trips that end the session - the rate-limit
    # exit. `None` keeps the pre-existing behaviour of backing off forever.
    # Details: docs/dev/core/config.md#stop_after_rate_limit_trips
    stop_after_rate_limit_trips: Optional[int] = 3
    # Run the LLM synthesis passes even when the session stopped early.
    # Details: docs/dev/core/config.md#synthesize_on_partial
    synthesize_on_partial: bool = False
    # Where per-run debug artifacts go, including each visited URL's
    # *.history.md markdown snapshots; "" disables debug logging entirely.
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
