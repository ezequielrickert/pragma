"""The `pragma dynamic` entry point: resume-from-DB, family-aware
interaction over a site.

Deliberately its own class, not a mode on `Engine` - `Engine._run_async`
still fuses discovery and interaction into one pass with no resume
capability. `DynamicEngine` resumes from whatever `pragma static` (and,
if it ran, `pragma cluster`) already wrote: when the graph store has
pages left `"Scouted"`, this interacts with exactly those, skipping
redundant clicks/fills two ways - a canonical `Component` reused across
pages is interacted with once, ever, its outcome inferred onto every
other page it renders on (`analysis/exact_reuse_index.py::
ExactReuseIndex`, issue #140), while a merely similar, genuinely distinct
component belonging to a known family is sample-and-skip capped instead
(`analysis/family_sampling.py::FamilySampler`). When it doesn't - no
prior `pragma static` run for this site - it falls back to independent
full discovery+interaction, the same fused behavior `Engine` has always
run. Details: docs/dev/core/dynamic_engine.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from analysis.exact_reuse_index import ExactReuseIndex
from analysis.family_sampling import DEFAULT_MAX_SAMPLES_PER_FAMILY, FamilySampler
from generators.ledger import flat_component_ledger
from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from spiders.browser.login import ensure_login_session
from spiders.content.fill_value_agent import make_ai_fill_value_fn
from spiders.content.fill_values import default_placeholder_fill_value
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import CrawlBudget, MechanicalCrawler, MechanicalCrawlerConfig
from .config import PragmaConfig
from .graph_store_resolution import resolve_graph_store
from .interfaces import Agent
from .registry import AGENT_REGISTRY


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class DynamicRunResult:
    """`DynamicEngine.run()`'s return value - a summary of what landed in
    the graph store, not a document (dynamic generates none).
    Details: docs/dev/core/dynamic_engine.md#dynamicrunresult
    """

    site: str
    resumed_from_static: bool
    pages_finished: int
    pages_total: int
    families_sampled: int
    instances_skipped: int
    exact_reuse_skipped: int


class DynamicEngine:
    """Wires an agent and a graph store, then interacts with one site's
    frontier - resuming from a prior `pragma static` run when one exists,
    falling back to independent discovery+interaction when it doesn't.
    Details: docs/dev/core/dynamic_engine.md#dynamicengine
    """

    def __init__(
        self,
        agent: Agent,
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
        interaction_timeout_seconds: Optional[float] = 10.0,
        wait_seconds: float = 1.0,
        interaction_wait_seconds: Optional[float] = None,
        ai_fill_values: bool = True,
        login_enabled: bool = True,
        login_session_max_age_hours: float = 24.0,
        max_samples_per_family: int = DEFAULT_MAX_SAMPLES_PER_FAMILY,
        mode: str = "stateful",
    ) -> None:
        self.agent = agent
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
        self.interaction_timeout_seconds = interaction_timeout_seconds
        self.wait_seconds = wait_seconds
        self.interaction_wait_seconds = interaction_wait_seconds
        self.ai_fill_values = ai_fill_values
        self.login_enabled = login_enabled
        self.login_session_max_age_hours = login_session_max_age_hours
        self.max_samples_per_family = max_samples_per_family
        self.mode = mode

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "DynamicEngine":
        """Resolve the agent and graph store named in `config` and wire a
        DynamicEngine around them. Same site-derivation convention as
        `Engine.from_config`/`StaticEngine.from_config`
        (`urlparse(url).netloc`) - the on-disk key this resumes against.
        Details: docs/dev/core/dynamic_engine.md#from_config
        """
        provider_options = config.agents.get(config.agent, {})
        try:
            agent = AGENT_REGISTRY.create(config.agent, **provider_options)
        except Exception as exc:
            print(f"Failed to initialize {config.agent} agent: {exc}; falling back to mock")
            agent = AGENT_REGISTRY.create("mock")

        site = urlparse(config.url).netloc if config.url else ""
        store_options = config.graph_stores.get(config.graph_store, {})
        graph_store = resolve_graph_store(config.graph_store, site, store_options)

        return cls(
            agent,
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
            interaction_timeout_seconds=config.interaction_timeout_seconds,
            wait_seconds=config.wait_seconds,
            interaction_wait_seconds=config.interaction_wait_seconds,
            ai_fill_values=config.ai_fill_values,
            login_enabled=config.login_enabled,
            login_session_max_age_hours=config.login_session_max_age_hours,
            mode=config.mode,
        )

    def _build_matching_state(self) -> tuple[Optional[FamilySampler], int, Optional[ExactReuseIndex]]:
        """`(sampler, families_found, exact_reuse_index)` from whatever
        `pragma static`/`pragma cluster` already wrote for this site -
        `exact_reuse_index` needs only the component ledger (a component
        can be exact-tier reused via write-time collapse alone, without
        clustering ever running), `sampler` additionally needs
        `ComponentFamily` records. Both `None` when their own
        prerequisite is missing, so neither `should_interact` nor
        `ExactReuseIndex.lookup` is ever consulted and every component
        gets interacted with as it always did before either ticket.
        Details: docs/dev/core/dynamic_engine.md#_build_matching_state
        """
        components = flat_component_ledger(self.graph_store)
        if not components:
            return None, 0, None
        exact_reuse_index = ExactReuseIndex(components)
        families = self.graph_store.get_component_families()
        if not families:
            return None, 0, exact_reuse_index
        sampler = FamilySampler(families, components, self.max_samples_per_family)
        return sampler, len(families), exact_reuse_index

    async def run(self, url: str) -> DynamicRunResult:
        """Interact with `url`'s site: resumes from whatever `pragma
        static` left `"Scouted"` when there is any, sampling known
        families rather than trusting every instance; falls back to a
        fused independent discovery+interaction crawl (today's `Engine`
        behavior) when the graph store has nothing scouted yet.
        Details: docs/dev/core/dynamic_engine.md#run
        """
        site = self.site or urlparse(url).netloc
        resumed = bool(self.graph_store.get_scouted())
        family_sampler: Optional[FamilySampler] = None
        exact_reuse_index: Optional[ExactReuseIndex] = None
        families_sampled = 0
        if resumed:
            family_sampler, families_sampled, exact_reuse_index = self._build_matching_state()

        session_path = None
        if self.login_enabled:
            session_path = await ensure_login_session(
                url, site, max_age_hours=self.login_session_max_age_hours, headless=self.headless
            )

        sink = GraphStoreSink(
            self.graph_store, base_url=url, allow_subdomains=self.allow_subdomains, run_id=_timestamp(),
        )
        fill_value_fn = (
            make_ai_fill_value_fn(self.agent) if self.ai_fill_values else default_placeholder_fill_value
        )
        crawler_config = Crawl4AICrawlerConfig(
            headless=self.headless,
            wait_seconds=self.wait_seconds,
            interaction_wait_seconds=self.interaction_wait_seconds,
            storage_state_path=session_path,
            block_images=self.block_images,
            page_timeout_seconds=self.page_timeout_seconds,
            navigation_watchdog_seconds=self.navigation_watchdog_seconds,
            session_cleanup_timeout_seconds=self.session_cleanup_timeout_seconds,
            interaction_timeout_seconds=self.interaction_timeout_seconds,
            mode=self.mode,
        )
        async with Crawl4AICrawler(crawler_config) as crawler:
            mechanical = MechanicalCrawler(
                crawler,
                config=MechanicalCrawlerConfig(
                    sink=sink,
                    fill_value_fn=fill_value_fn,
                    max_pages=self.max_pages,
                    budget=self.crawl_budget,
                    page_concurrency=self.page_concurrency,
                    base_url=url,
                    allow_subdomains=self.allow_subdomains,
                    interact_only=resumed,
                    family_sampler=family_sampler,
                    exact_reuse_index=exact_reuse_index,
                ),
            )
            await mechanical.crawl_site(url)

        finished_pages, total_pages = self.graph_store.count_visited()
        instances_skipped = len(family_sampler.skipped) if family_sampler else 0
        exact_reuse_skipped = len(exact_reuse_index.skipped) if exact_reuse_index else 0
        self.graph_store.close()
        return DynamicRunResult(
            site=site,
            resumed_from_static=resumed,
            pages_finished=finished_pages,
            pages_total=total_pages,
            families_sampled=families_sampled,
            instances_skipped=instances_skipped,
            exact_reuse_skipped=exact_reuse_skipped,
        )
