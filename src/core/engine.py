"""The Engine: Pragma's micro-kernel. Resolves plugins and runs one job."""
from __future__ import annotations

from datetime import datetime, timezone

from ..utils.io import write_output
from .config import PragmaConfig
from .interfaces import Agent, PRDGenerator, Scraper
from .registry import AGENT_REGISTRY, GENERATOR_REGISTRY, SCRAPER_REGISTRY


def _slugify(url: str) -> str:
    """Turn URL into a filesystem-safe slug."""
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def _timestamp() -> str:
    """Generate a standard timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Engine:
    """Wires a scraper, an agent, and a generator strategy, then runs them."""

    def __init__(
        self, scraper: Scraper, agent: Agent, generator: PRDGenerator, out_dir: str = "docs"
    ) -> None:
        self.scraper = scraper
        self.agent = agent
        self.generator = generator
        self.out_dir = out_dir

    @classmethod
    def from_config(cls, config: PragmaConfig) -> "Engine":
        """Resolve and wire plugins named in config via the registries."""
        slug = _slugify(config.url)
        log_path = f"{config.logs_dir}/{slug}_research_{_timestamp()}.md"

        scraper = SCRAPER_REGISTRY.create(config.scraper, headless=config.headless)

        provider_options = config.agents.get(config.agent, {})
        try:
            agent = AGENT_REGISTRY.create(config.agent, **provider_options)
        except Exception as exc:
            print(f"Failed to initialize {config.agent} agent: {exc}; falling back to mock")
            agent = AGENT_REGISTRY.create("mock")

        generator = GENERATOR_REGISTRY.create(
            config.generator,
            agent=agent,
            scraper=scraper,
            progress_file=log_path,
            max_iterations=config.max_iterations,
        )
        return cls(scraper, agent, generator, out_dir=config.out_dir)

    def run(self, url: str) -> str:
        """Run the wired strategy on a URL; write and return the PRD path."""
        prd = self.generator.generate_prd(url)
        prd_path = f"{self.out_dir}/{_slugify(url)}_prd_{_timestamp()}.md"
        write_output(prd_path, prd)
        return prd_path
