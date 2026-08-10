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

    `agents` holds optional per-provider settings (model, endpoint, etc.), keyed by
    provider name, e.g. {"gemini": {"model": "..."}}. Secrets should stay in env
    vars / .env; `agents` is meant for non-secret, provider-specific overrides that
    would otherwise clutter a single flat .env as more providers are added. Each
    provider is still free to fall back to its own env vars when a key is omitted
    here - see the Config dataclasses colocated with each Agent implementation.
    """

    url: Optional[str] = None
    agent: str = "openai"
    graph_store: str = "memory"
    out_dir: str = "docs"
    headless: bool = True
    # Extra time to let a page settle before discovery reads it - carried
    # over from PlaywrightScraper's own `wait_seconds`. Confirmed necessary
    # against a real JS-heavy SPA (empanad.app): the default `wait_for` alone
    # is satisfied by the pre-hydration HTML shell, so discovery can read 0
    # components/links on a page that has real ones once actually rendered.
    # Default is deliberately small; raise it for slow/JS-heavy sites.
    wait_seconds: float = 2.0
    # Same purpose as wait_seconds, but applied after a click/fill's own
    # re-discovery instead of a full page's first load. None (default) falls
    # back to wait_seconds unchanged. Worth setting lower once a site's
    # confirmed to settle a same-page DOM update faster than its initial
    # hydration - measured live: every interaction pays this wait, so it's
    # usually the single largest fixed cost in a real crawl's wall-clock time
    # (a page with a few dozen components pays it a few dozen times).
    interaction_wait_seconds: Optional[float] = None
    # crawl4ai's own raw navigation/goto dead-page timeout (page_timeout,
    # converted to ms at the Crawl4AICrawler boundary) - NOT the same phase
    # as wait_seconds/interaction_wait_seconds above (those apply *after* a
    # page has already loaded; this bounds the underlying goto()/js_only
    # call itself). crawl4ai's own default is 60s - fine for correctness,
    # wasteful once a request is genuinely hung/dead. Keep this comfortably
    # above wait_seconds/interaction_wait_seconds's own scale - setting it
    # too low reintroduces the pre-hydration-shell "0 components discovered"
    # bug via a different code path (a slow-but-alive real SPA load getting
    # killed before it ever finishes). See Crawl4AICrawler's own
    # page_timeout_seconds docstring.
    page_timeout_seconds: float = 15.0
    # Skips crawl4ai's own markdown-generation/content-scraping pipeline
    # (crawl4ai's `prefetch` option) - real savings, since this project never
    # reads that pipeline's output (all facts come from this project's own
    # discovery JS instead). One real side effect: `debug_logs/*/pages/*.md`
    # snapshots (crawl4ai's markdown conversion of each page) come back
    # empty while this is on - leave False during an active debugging
    # session that still wants to read those; True for a bulk/production
    # run. See Crawl4AICrawler's own prefetch docstring.
    prefetch: bool = False
    # Aborts image/media/font network requests outright via a Playwright
    # page.route() handler - real bandwidth/load-time savings, unlike
    # crawl4ai's own exclude_external_images (which only strips already-
    # downloaded images from crawl4ai's own output; see Crawl4AICrawler's
    # block_images docstring for why that flag does nothing for this
    # project). A real behavior change (a site whose interactive elements
    # depend on images actually loading could behave differently) - off by
    # default, opt in per-site once confirmed safe.
    block_images: bool = False
    # Per-page cap on how many components MechanicalCrawler mechanically
    # interacts with in a single visit-pass - the backstop against a
    # pathological reveal-chain, not a normal-case limiter (default generous
    # enough that ordinary pages never hit it). See
    # src/crawlers/mechanical_loop.py's module docstring.
    element_budget: int = 200
    # Total pages MechanicalCrawler.crawl_site will visit before stopping,
    # None = unbounded (crawl until the URL frontier is exhausted). A page
    # re-queued after a navigation-interrupted pass (see
    # PageVisitResult.interrupted_by_navigation) counts as its own visit here.
    max_pages: Optional[int] = None
    # Max times MechanicalCrawler will revisit the same page to keep draining
    # its interaction frontier (a page whose components exceed element_budget
    # needs more than one pass) before giving up on it gracefully. Backstop
    # against a page that keeps generating genuinely new content faster than
    # one pass's budget can keep up with (infinite-scroll/live-chat-style) -
    # same "backstop against a pathological case" philosophy as
    # element_budget itself.
    max_passes_per_page: int = 10
    # Backstop against a site that mints a fresh, per-visit-token URL (e.g. a
    # `/o/<random-hash>` order flow) on essentially every top-level visit -
    # confirmed live on empanad.app: each token is a distinct real identity
    # (clean_url() correctly keeps them apart), so an unbounded frontier
    # would treat every new token as a brand-new page forever and never
    # converge, burning a full interaction pass on what's structurally the
    # same page every time. `route_shape()` (src/utils/urls.py) collapses
    # same-shaped URLs for this bounding check only - real navigation/
    # identity is untouched. Default 1: an ordinary site has no repeated
    # route shapes at all, so this never fires; raise it to deliberately
    # sample more than one instance of a session-token route. See
    # MechanicalCrawler.max_visits_per_route_shape.
    max_visits_per_route_shape: int = 1
    # Whether MechanicalCrawler asks `agent` to generate a realistic fill
    # value for each fillable field (a real network+generation round trip
    # per field - can dominate wall-clock time against a slow/remote model).
    # False falls back to the fast, deterministic placeholder instead - set
    # this off for a speed-focused run that doesn't need realistic fill
    # values in the output.
    ai_fill_values: bool = True
    # How many pages MechanicalCrawler.crawl_site visits concurrently.
    # Default 1 keeps the original fully-sequential crawl (every earlier
    # behavior/guarantee holds exactly as before) - raise it to actually cut
    # wall-clock time on a large site: fixed per-interaction waits
    # (wait_seconds/interaction_wait_seconds) are what make a sequential
    # crawl slow in practice, and they overlap across concurrently-visited
    # pages instead of serializing. See MechanicalCrawler's own docstring for
    # what this changes under the hood and its tradeoffs (a soft, not hard,
    # bound on max_pages once concurrency > 1).
    page_concurrency: int = 1
    # Whether same-site scoping (which links MechanicalCrawler's URL frontier
    # will actually visit - see src/utils/urls.py's is_in_scope(), the single
    # choke point in MechanicalCrawler._enqueue()) treats a subdomain (e.g.
    # blog.example.com) as in-scope for a crawl of example.com. A link (or a
    # click/redirect landing) on any *other* host is always out of scope,
    # regardless of this setting - the interaction/edge that led there is
    # still recorded, it's just never itself crawled further. Off by default:
    # exact host match only. A naive last-two-label heuristic when enabled,
    # not a full public-suffix-list lookup.
    allow_subdomains: bool = False
    # Purge this site's previously recorded graph_store state before crawling
    # (Engine.from_config). Matters for graph_store: neo4j, which persists
    # across runs - without this, a site whose URLs are per-session tokens
    # (e.g. a `/o/<random-id>` order flow) accumulates a "visited" node per
    # past run forever, none of which will ever be seen again but all of
    # which the synthesis step still reads back as history. graph_store: memory
    # never persists across runs regardless, so this is a no-op there either
    # way. Set to false to resume a previous run's progress on a genuinely
    # multi-session crawl of a large, stable site.
    fresh: bool = True
    # Where per-run debug artifacts go: debug_logs/{slug}_{timestamp}/debug.md
    # (every crawl4ai hook firing, appended live) and .../pages/{page}.md
    # (crawl4ai's own markdown conversion of each page, last-seen snapshot).
    # Set to "" (empty string) to disable debug logging entirely - see
    # src/crawlers/debug_log.py and Engine._run_async.
    debug_logs_dir: str = "debug_logs"
    # Max number of past debug_logs_dir run directories to keep for this same
    # site+URL (see src/crawlers/debug_log.py::prune_old_runs), oldest
    # deleted first. None (default) keeps every run forever, unchanged from
    # before this setting existed - opt in once unbounded debug_logs/ growth
    # becomes a real disk-space concern for a site crawled repeatedly. A
    # no-op whenever debug_logs_dir is disabled (there's nothing to prune).
    debug_logs_keep_last: Optional[int] = None
    # Also write docs/{slug}_graph_{timestamp}.json - the full crawl graph
    # (pages, edges, component ledger, text content) as structured JSON,
    # alongside the prose PRD and the ASCII component tree - for a downstream
    # tool that wants to consume the crawl's facts as data instead of
    # documents meant for a person to read. Off by default so existing
    # `out_dir` layouts don't suddenly grow an extra file per run without
    # opting in. See src/generators/graph_export.py.
    export_json: bool = False
    # Component-tree document (docs/{slug}_tree_{timestamp}.md) rendering
    # mode - Unicode box-drawing characters (tree command style) by default;
    # True falls back to plain ASCII for terminals/environments that mangle
    # Unicode. See src/generators/component_tree.py::render_ascii_tree.
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
        """Build a PragmaConfig by merging env vars, an optional YAML file, and CLI flags.

        Precedence (highest wins): explicit CLI flag > YAML file value > env var > default.
        """
        cfg = cls()
        cfg._apply_env()
        cfg._apply_yaml(yaml_path)
        cfg._apply_overrides(cli_overrides)
        return cfg
