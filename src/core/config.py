"""Layered configuration: defaults < env vars < YAML file < explicit CLI flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

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
    graph_store: str = "memory"
    out_dir: str = "docs"
    logs_dir: str = "research_logs"
    progress_logs_dir: str = "progress_logs"
    graph_logs_dir: str = "graph_logs"
    headless: bool = True
    max_iterations: int = 12
    wait_seconds: float = 15.0
    batch_size: int = 20
    # Independent overrides for the two budgets `batch_size` otherwise double-spends
    # (pending routes shown per prompt vs. DNA components shown per prompt) - a
    # component-dense page (a mega-nav with hundreds of elements) competing with a
    # route-heavy site's pending-page queue for the same shared number can run out
    # of `max_iterations` before its long tail of components is ever even shown.
    # None means "fall back to batch_size" - see SimplePRDGenerator.__init__.
    pending_batch_size: Optional[int] = None
    component_batch_size: Optional[int] = None
    # Whether same-domain scoping (which links get queued as pending routes)
    # treats a subdomain (e.g. blog.example.com) as in-scope for a crawl of
    # example.com. Off by default - matches the pre-existing exact-netloc-match
    # behavior. A naive last-two-label heuristic when enabled, not a full
    # public-suffix-list lookup (see SimplePRDGenerator._domain_in_scope).
    allow_subdomains: bool = False
    # How many consecutive times a page's unexplored-component debt can fail
    # to shrink before the finish guard gives up on that page - see
    # SimplePRDGenerator._apply_diminishing_returns. Protects against a
    # component whose CSS path shifts on every DOM change (e.g. a quantity
    # stepper) or a real interaction whose outcome never changes (e.g. a login
    # retried against invalid credentials), either of which could otherwise
    # burn most of a run's iteration budget on one page that was never going
    # to converge.
    max_stalled_finish_attempts: int = 3
    # Purge this site's previously recorded graph_store state before crawling
    # (Engine.from_config). Matters for graph_store: neo4j, which persists
    # across runs - without this, a site whose URLs are per-session tokens
    # (e.g. a `/o/<random-id>` order flow) accumulates a "visited" node per
    # past run forever, none of which will ever be seen again but all of
    # which the next run's plan/synthesis steps still read back as history.
    # graph_store: memory never persists across runs regardless, so this is a
    # no-op there either way. Set to false to resume a previous run's
    # progress on a genuinely multi-session crawl of a large, stable site.
    fresh: bool = True
    # Read a deeper "what is this site/app for" text from the root page once, at the
    # start of Discovery, and surface it on every iteration prompt - see
    # SimplePRDGenerator._establish_site_context. Grounds fill-value/action choices in
    # the site's actual purpose (e.g. an empanada-ordering site never gets "lapicera"
    # typed into a flavor field) instead of only ever seeing route names and short
    # per-page descriptions. No extra LLM call - the scraper's own extracted text is
    # used directly (see that method's docstring for why). Default on; set false to
    # skip the extra page read (e.g. a very slow site, or a root page whose content
    # isn't representative of the rest of the app).
    deep_context: bool = True
    context_max_chars: int = 1500
    # Regex patterns (re.fullmatch against one path segment at a time, domain
    # segment never a candidate) marking a URL path segment as per-visit/dynamic
    # rather than a real distinct route - e.g. an order confirmation page whose
    # URL embeds a random token (`/o/<token>`). A matching segment is replaced
    # with the literal placeholder `{id}` before the URL becomes a graph-node
    # key, so every visit collapses into one node instead of minting a new one
    # per token. Empty by default - opt-in per site, see
    # SimplePRDGenerator._normalize_dynamic_segments and
    # docs/explicativos/neo4j.md's "Problema conocido" section.
    dynamic_url_segments: List[str] = field(default_factory=list)
    # Whether query strings are dropped entirely from the graph-node key by
    # default - most (tracking/session tokens) don't represent meaningfully
    # different content. See SimplePRDGenerator._normalize_query.
    strip_query_params: bool = True
    # Query param names to keep even when strip_query_params is True, for a site
    # where a specific param genuinely changes page content (e.g. `?page=2`).
    keep_query_params: List[str] = field(default_factory=list)
    # Fetch/parse /sitemap.xml once, before crawling starts, queuing every
    # in-scope URL found there as a Pending route - a near-zero-cost way to learn
    # a large site's breadth without spending agent iterations discovering it via
    # clicks. Best-effort: a missing/unreachable/malformed sitemap never fails
    # the run. See SimplePRDGenerator._seed_from_sitemap.
    use_sitemap: bool = True
    # Fraction (0.0-1.0) of max_iterations reserved for a breadth-first pass that
    # prioritizes visiting at least one route from every not-yet-seen top-level
    # section before spending the remaining budget drilling into any one
    # section's depth (ranked instead by incoming-link count once elapsed). See
    # SimplePRDGenerator._order_pending.
    skeleton_fraction: float = 0.3
    # Block (rather than execute) a click/submit that looks like it would mutate
    # real state - a form submitting via POST, or text matching a business-
    # mutation verb (comprar/eliminar/confirmar/buy/delete/...) - recording that
    # a mutation point exists there instead. fill is never blocked. Default on,
    # matching this project's own backlog (feedback.md: "que no haga mutaciones,
    # que no cambie el estado"). See SimplePRDGenerator.safe_mode / --unsafe.
    safe_mode: bool = True
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
        """Build a PragmaConfig by merging env vars, an optional YAML file, and CLI flags.

        Precedence (highest wins): explicit CLI flag > YAML file value > env var > default.
        """
        cfg = cls()
        cfg._apply_env()
        cfg._apply_yaml(yaml_path)
        cfg._apply_overrides(cli_overrides)
        return cfg
