"""Layered configuration: defaults < env vars < YAML file < explicit CLI flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

import yaml

# Where `load()` looks when no --config is passed, in order. The first entry
# is what `core/wizard.py` writes, and the two disagreed between cc8273d and
# now - the wizard wrote pragma.yaml while this module read config/pragma.yaml
# only, so a wizard-generated config was silently ignored on every run. Both
# are honored so neither existing layout breaks.
# Details: docs/dev/core/config.md#default_config_paths
DEFAULT_CONFIG_PATHS = ("pragma.yaml", "config/pragma.yaml")


@dataclass
class PragmaConfig:
    """Wiring configuration for the Engine (which plugins, and crawl-tuning settings).
    Details: docs/dev/core/config.md#pragmaconfig
    """

    url: Optional[str] = None
    agent: str = "local"
    graph_store: str = "memory"
    out_dir: str = "data/output"
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
    # Total pages before stopping; None = unbounded.
    # Details: docs/dev/core/config.md#max_pages
    max_pages: Optional[int] = None
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
    # has (see docs/dev/spiders/orchestration/mechanical_loop/loop.md), paired with
    # MechanicalCrawlerConfig's own memory_ceiling_percent so more workers
    # don't just trade wall-clock time for the same OOM risk.
    # Details: docs/dev/core/config.md#page_concurrency
    page_concurrency: int = 4
    # Whether a subdomain counts as in-scope for MechanicalCrawler's frontier.
    # Details: docs/dev/core/config.md#allow_subdomains
    allow_subdomains: bool = False
    # Purge this site's previous graph_store state before crawling.
    # Details: docs/dev/core/config.md#fresh
    fresh: bool = True
    # Where per-run debug artifacts go, including each visited URL's
    # *.history.md markdown snapshots; "" disables debug logging entirely.
    # Details: docs/dev/core/config.md#debug_logs_dir
    debug_logs_dir: str = "data/debug_logs"
    # Max past debug_logs_dir run directories to keep for this site+URL.
    # Details: docs/dev/core/config.md#debug_logs_keep_last
    debug_logs_keep_last: Optional[int] = None
    # Also write the full crawl graph as structured JSON. Kept as its own
    # flag rather than folded into `documents` below so an existing
    # pragma.yaml keeps working unchanged; `true` appends "export" to the
    # document list. Details: docs/dev/core/config.md#export_json
    export_json: bool = False
    # Which output documents to generate, by DOCUMENT_REGISTRY name, in
    # order. The master document ("Start Here") always runs last and is
    # not listed here - it is the pipeline's closing step, not an optional
    # document. Details: docs/dev/core/config.md#documents
    documents: List[str] = field(default_factory=lambda: ["coverage", "prd", "tree", "openapi", "catalog", "flows", "usability", "tokens", "accessibility", "gherkin", "sequences"])
    # Re-visit the crawled pages once more with images on and a realistic
    # viewport, running the accessibility audit. Costs one extra navigation
    # per page and no interaction; off by default because it is only worth
    # paying for when the accessibility/design documents are wanted.
    # Details: docs/dev/core/config.md#measurement_pass
    measurement_pass: bool = False
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

    def _default_yaml_path(self) -> Optional[Path]:
        """First existing path in `DEFAULT_CONFIG_PATHS`, or `None`.
        Details: docs/dev/core/config.md#_default_yaml_path
        """
        return next((p for p in (Path(c) for c in DEFAULT_CONFIG_PATHS) if p.exists()), None)

    def _apply_yaml(self, yaml_path: Optional[str]) -> None:
        if yaml_path:
            path = Path(yaml_path)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {yaml_path}")
        else:
            path = self._default_yaml_path()
            if path is None:
                return

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        valid = {f.name for f in fields(self)}
        for key, val in data.items():
            if key in valid and val is not None:
                setattr(self, key, val)
        print(f"Loaded config from {path}")

        # Named, not just counted: an ignored key is almost always a typo or a
        # setting that was renamed out from under an existing file, and both
        # are invisible otherwise. `max_iterations: 40` sat in this repo's own
        # pragma.yaml bounding nothing at all - the run it was meant to cap
        # went 12 hours. Details: docs/dev/core/config.md#_apply_yaml-unknown-keys
        unknown = sorted(key for key in data if key not in valid)
        if unknown:
            print(f"Warning: {path} has {len(unknown)} setting(s) this version does not know, ignored:")
            for key in unknown:
                print(f"  {key} - see config/pragma.example.yaml for the current names")

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
