"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one job."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from ..utils.io import write_output
from .config import PragmaConfig
from .interfaces import Agent, GraphStore, PRDGenerator, Scraper
from .registry import AGENT_REGISTRY, GENERATOR_REGISTRY, GRAPH_STORE_REGISTRY, SCRAPER_REGISTRY


def _slugify(url: str) -> str:
    """Turn URL into a filesystem-safe slug."""
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def _timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Engine:
    """Wires a scraper, an agent, and a generator strategy, then runs them."""

    def __init__(
        self,
        scraper: Scraper,
        agent: Agent,
        generator: PRDGenerator,
        out_dir: str = "docs",
        graph_store: Optional[GraphStore] = None,
    ) -> None:
        self.scraper = scraper
        self.agent = agent
        self.generator = generator
        self.out_dir = out_dir
        self.graph_store = graph_store

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "Engine":
        """Resolve and wire plugins named in config via the registries."""
        slug = _slugify(config.url)
        timestamp = _timestamp()
        log_path = f"{config.logs_dir}/{slug}_research_{timestamp}.md"
        progress_log_path = f"{config.progress_logs_dir}/{slug}_progress_{timestamp}.md"
        graph_log_path = f"{config.graph_logs_dir}/{slug}_graph_{timestamp}.json"
        # Same folder as the navigation graph - both are machine-readable JSON
        # debug artifacts written once at the end of a run; a new config
        # dimension (its own dir/CLI flag) for one more file felt like more
        # ceremony than the addition warranted.
        components_log_path = f"{config.graph_logs_dir}/{slug}_components_{timestamp}.json"
        components_catalog_path = f"{config.graph_logs_dir}/{slug}_component_catalog_{timestamp}.md"

        scraper = SCRAPER_REGISTRY.create(
            config.scraper, headless=config.headless, wait_seconds=config.wait_seconds
        )

        provider_options = config.agents.get(config.agent, {})
        try:
            agent = AGENT_REGISTRY.create(config.agent, **provider_options)
        except Exception as exc:
            print(f"Failed to initialize {config.agent} agent: {exc}; falling back to mock")
            agent = AGENT_REGISTRY.create("mock")

        store_options = config.graph_stores.get(config.graph_store, {})
        try:
            graph_store = GRAPH_STORE_REGISTRY.create(config.graph_store, **store_options)
            graph_store.connect()
        except Exception as exc:
            print(f"Failed to initialize {config.graph_store} graph store: {exc}; falling back to memory")
            graph_store = GRAPH_STORE_REGISTRY.create("memory")
            graph_store.connect()

        if config.fresh:
            site = urlparse(config.url).netloc
            if site:
                # No-op for InMemoryGraphStore (nothing persists across runs there
                # anyway) - matters for graph_store: neo4j, see PragmaConfig.fresh's
                # docstring for why this defaults to on.
                graph_store.clear_site(site)

        generator = GENERATOR_REGISTRY.create(
            config.generator,
            agent=agent,
            scraper=scraper,
            graph_store=graph_store,
            progress_file=log_path,
            progress_log_file=progress_log_path,
            graph_log_file=graph_log_path,
            components_log_file=components_log_path,
            components_catalog_file=components_catalog_path,
            max_iterations=config.max_iterations,
            batch_size=config.batch_size,
            pending_batch_size=config.pending_batch_size,
            component_batch_size=config.component_batch_size,
            allow_subdomains=config.allow_subdomains,
            max_stalled_finish_attempts=config.max_stalled_finish_attempts,
            deep_context=config.deep_context,
            context_max_chars=config.context_max_chars,
        )
        return cls(scraper, agent, generator, out_dir=config.out_dir, graph_store=graph_store)

    def run(self, url: str) -> str:
        """Run the wired strategy on a URL; write and return the PRD path."""
        prd = self.generator.generate_prd(url)
        prd_path = f"{self.out_dir}/{_slugify(url)}_prd_{_timestamp()}.md"
        write_output(prd_path, prd)
        return prd_path
