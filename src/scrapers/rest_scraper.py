"""REST-backed scraper: implements `Scraper` by calling Module 3 (`src/api_server/`) over plain
synchronous HTTP instead of driving `PlaywrightScraper` in-process.

Every public method here keeps the same signature and raise-on-real-failure contract as
`PlaywrightScraper` (src/scrapers/playwright_scraper.py), so `SimplePRDGenerator` and
`_dna_index_map`'s ref->selector resolution are unaffected by which scraper backend is selected.

Unlike the removed MCP-backed scraper, this needs no event loop or background thread - `requests`
(already a hard dependency) is synchronous, so every method here is a plain blocking HTTP call.
That's the concrete simplification the REST pivot buys: see ARCHITECTURE.md's "Module 3: Unified
REST API" for why. Module 3 is a standing service this class doesn't own the lifecycle of, so
`close()` is deliberately a no-op - killing the orchestrator run should not kill the shared
browser session.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import requests

from ..core.interfaces import PageState, Scraper
from ..core.registry import SCRAPER_REGISTRY


@dataclass
class RestConfig:
    """Where RestScraper's settings come from - the only place that reads PRAGMA_API_* env vars.

    Mirrors `LocalConfig.from_env()` (src/agents/local_agent.py) for the same per-provider config
    isolation described in ARCHITECTURE.md's "Per-Provider Config Encapsulation" section.
    """

    base_url: str = field(default_factory=lambda: os.getenv("PRAGMA_API_URL", "http://127.0.0.1:8765"))

    @classmethod
    def from_env(cls) -> "RestConfig":
        return cls()


@SCRAPER_REGISTRY.register("rest")
class RestScraper(Scraper):
    """A `Scraper` that executes actions through Module 3's `/dynamic/*` REST API."""

    def __init__(
        self,
        headless: bool = True,
        wait_seconds: float = 15.0,
        config: Optional[RestConfig] = None,
    ) -> None:
        """Accepts the same `headless`/`wait_seconds` kwargs `Engine.from_config` passes to every
        scraper (see engine.py's `SCRAPER_REGISTRY.create` call) so this backend is a drop-in swap
        for `PlaywrightScraper` in `pragma.yaml` - but they're intentionally unused here. Module 3
        is a standing service with its own startup config (`PRAGMA_API_HEADLESS`/
        `PRAGMA_API_WAIT_SECONDS`, read once when the server process starts), not something a
        per-run client can override after the fact - see ARCHITECTURE.md's "Module 3" lifecycle
        section for why.
        """
        self.config = config or RestConfig.from_env()
        self._session = requests.Session()

    def _post(self, path: str, payload: dict) -> PageState:
        response = self._session.post(f"{self.config.base_url}{path}", json=payload, timeout=60)
        return self._to_page_state(response)

    def _get(self, path: str) -> PageState:
        response = self._session.get(f"{self.config.base_url}{path}", timeout=60)
        return self._to_page_state(response)

    @staticmethod
    def _to_page_state(response: requests.Response) -> PageState:
        if not response.ok:
            detail = response.json().get("detail", response.text) if response.content else response.reason
            raise RuntimeError(f"Module 3 request failed ({response.status_code}): {detail}")
        return PageState(**response.json())

    # Known gap, not yet implemented: unlike PlaywrightScraper.click/fill/submit,
    # these don't accept a `frame_url` kwarg for targeting a component discovered
    # inside an iframe - Module 3's `/dynamic/*` routes have no frame-targeting
    # parameter yet. SimplePRDGenerator only ever passes `frame_url` when it's
    # non-empty (see `_execute_action`), so every non-iframe component - the
    # overwhelming common case - is unaffected; a click/fill/submit against a
    # real iframe component through this backend fails with a clear TypeError,
    # caught by `_execute_action`'s existing try/except (skips that iteration
    # rather than crashing the run) instead of silently landing on the wrong
    # document.

    def navigate(self, url: str) -> PageState:
        return self._post("/dynamic/navigate", {"url": url})

    def click(self, selector: str) -> PageState:
        return self._post("/dynamic/click", {"selector": selector})

    def fill(self, selector: str, value: str) -> PageState:
        return self._post("/dynamic/fill", {"selector": selector, "value": value})

    def submit(self, selector: str) -> PageState:
        return self._post("/dynamic/submit", {"selector": selector})

    def get_state(self) -> PageState:
        return self._get("/dynamic/state")

    def close(self) -> None:
        """No-op: Module 3's browser session outlives any one orchestrator run - see this
        module's docstring."""
        self._session.close()


class DocsClient:
    """Fetches a curated `/static/*` topic from Module 3 - the `help` verb's execution side.

    Colocated with `RestScraper` (not a separate top-level module) since both are "how the
    orchestrator talks to Module 3," just different path prefixes on the same server. Used by
    `SimplePRDGenerator` when the model's `AgentAction.kind == "help"` (see prd_generator.py).
    """

    def __init__(self, config: Optional[RestConfig] = None) -> None:
        self.config = config or RestConfig.from_env()
        self._session = requests.Session()

    def get(self, topic: str) -> str:
        """Return the curated text for `topic`, or a short fallback if it's unknown/unreachable.

        Deliberately does not raise: a `help` lookup failing (server down, unknown topic) is not
        as severe as a real browser action failing - it should degrade to "no extra guidance this
        turn," not abort the run.
        """
        try:
            response = self._session.get(f"{self.config.base_url}/static/{topic}", timeout=10)
            if not response.ok:
                detail = response.json().get("detail", response.text)
                return f"(help unavailable for '{topic}': {detail})"
            return response.json()["content"]
        except requests.RequestException as exc:
            return f"(help unavailable: could not reach Module 3 at {self.config.base_url}: {exc})"
