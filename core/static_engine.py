"""The `pragma static` entry point: a scout-only, prefetch=true crawl.

Deliberately its own class, not a mode on `Engine` - `Engine._run_async`
fuses crawling with document generation, and static's whole point is
*not* doing that: it captures a site's real static content (HTML, CSS,
routes) into the graph store and stops there. `pragma cluster`,
`pragma dynamic`, and `pragma docs` (their own tickets) all resume from
what this writes, not from anything this class returns.
Details: docs/dev/core/static_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.browser.login import ensure_login_session
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import CrawlBudget, MechanicalCrawler, MechanicalCrawlerConfig
from .config import PragmaConfig
from .registry import GRAPH_STORE_REGISTRY


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class StaticRunResult:
    """`StaticEngine.run()`'s return value - a summary of what landed in
    the graph store, not a document (static generates none).
    Details: docs/dev/core/static_engine.md#staticrunresult
    """

    site: str
    pages_scouted: int
    pages_total: int
    login_session_path: Optional[str]


class StaticEngine:
    """Wires a graph store and runs one site's scout-only crawl.
    Details: docs/dev/core/static_engine.md#staticengine
    """

    def __init__(
        self,
        graph_store: Any,
        site: str = "",
        headless: bool = True,
        max_pages: Optional[int] = None,
        crawl_budget: Optional[CrawlBudget] = None,
        page_concurrency: int = 4,
        allow_subdomains: bool = False,
        block_images: bool = True,
        page_timeout_seconds: float = 15.0,
        navigation_watchdog_seconds: float = 60.0,
        session_cleanup_timeout_seconds: float = 10.0,
        login_enabled: bool = True,
        login_session_max_age_hours: float = 24.0,
    ) -> None:
        self.graph_store = graph_store
        self.site = site
        self.headless = headless
        self.max_pages = max_pages
        self.crawl_budget = crawl_budget or CrawlBudget()
        self.page_concurrency = page_concurrency
        self.allow_subdomains = allow_subdomains
        self.block_images = block_images
        self.page_timeout_seconds = page_timeout_seconds
        self.navigation_watchdog_seconds = navigation_watchdog_seconds
        self.session_cleanup_timeout_seconds = session_cleanup_timeout_seconds
        self.login_enabled = login_enabled
        self.login_session_max_age_hours = login_session_max_age_hours

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "StaticEngine":
        """Resolve the graph store named in `config` and wire a StaticEngine
        around it. Same site-derivation convention as `Engine.from_config`
        (`urlparse(url).netloc`, slugified by the store itself) - the
        on-disk key every later stage resumes against.
        Details: docs/dev/core/static_engine.md#from_config
        """
        site = urlparse(config.url).netloc if config.url else ""
        store_options = config.graph_stores.get(config.graph_store, {})
        try:
            graph_store = GRAPH_STORE_REGISTRY.create(config.graph_store, site=site, **store_options)
            graph_store.connect()
        except Exception as exc:
            print(f"Failed to initialize {config.graph_store} graph store: {exc}; falling back to memory")
            graph_store = GRAPH_STORE_REGISTRY.create("memory", site=site)
            graph_store.connect()

        if config.fresh and site:
            graph_store.reset()

        return cls(
            graph_store,
            site=site,
            headless=config.headless,
            max_pages=config.max_pages,
            crawl_budget=CrawlBudget(**config.crawl_budget),
            page_concurrency=config.page_concurrency,
            allow_subdomains=config.allow_subdomains,
            block_images=config.block_images,
            page_timeout_seconds=config.page_timeout_seconds,
            navigation_watchdog_seconds=config.navigation_watchdog_seconds,
            session_cleanup_timeout_seconds=config.session_cleanup_timeout_seconds,
            login_enabled=config.login_enabled,
            login_session_max_age_hours=config.login_session_max_age_hours,
        )

    async def run(self, url: str) -> StaticRunResult:
        """Scout every page reachable from `url`: real navigation,
        `prefetch=true`, no click/fill. Auto-triggers login first via
        `ensure_login_session` when the site turns out to be gated - a
        crash here would defeat the point of a first-class content-
        capture pass. Details: docs/dev/core/static_engine.md#run
        """
        site = self.site or urlparse(url).netloc
        session_path = None
        if self.login_enabled:
            session_path = await ensure_login_session(
                url, site, max_age_hours=self.login_session_max_age_hours, headless=self.headless
            )

        sink = GraphStoreSink(
            self.graph_store, base_url=url, allow_subdomains=self.allow_subdomains, run_id=_timestamp(),
        )
        crawler_config = Crawl4AICrawlerConfig(
            headless=self.headless,
            prefetch=True,
            storage_state_path=session_path,
            block_images=self.block_images,
            page_timeout_seconds=self.page_timeout_seconds,
            navigation_watchdog_seconds=self.navigation_watchdog_seconds,
            session_cleanup_timeout_seconds=self.session_cleanup_timeout_seconds,
        )
        async with Crawl4AICrawler(crawler_config) as crawler:
            mechanical = MechanicalCrawler(
                crawler,
                config=MechanicalCrawlerConfig(
                    sink=sink,
                    max_pages=self.max_pages,
                    budget=self.crawl_budget,
                    page_concurrency=self.page_concurrency,
                    base_url=url,
                    allow_subdomains=self.allow_subdomains,
                    scout_only=True,
                ),
            )
            await mechanical.crawl_site(url)

        pages_scouted = len(self.graph_store.get_scouted())
        _, pages_total = self.graph_store.count_visited()
        self.graph_store.close()
        return StaticRunResult(
            site=site,
            pages_scouted=pages_scouted,
            pages_total=pages_total,
            login_session_path=session_path,
        )
