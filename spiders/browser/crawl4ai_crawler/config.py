"""Every tuning knob Crawl4AICrawler accepts, bundled into one object.
Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..debug_log import CrawlDebugLog


@dataclass
class Crawl4AICrawlerConfig:
    """Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#crawl4aicrawlerconfig"""

    headless: bool = True
    wait_seconds: float = 2.0
    interaction_wait_seconds: Optional[float] = None
    debug_log: Optional[CrawlDebugLog] = None
    page_timeout_seconds: float = 15.0
    prefetch: bool = False
    block_images: bool = False
    # Viewport the browser renders at - small by design, since a smaller
    # viewport cuts render cost per navigation and nothing in this pipeline
    # needs a realistic one.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#viewport
    viewport_width: int = 800
    viewport_height: int = 600
    interaction_timeout_seconds: Optional[float] = None
    # Cap on the polite delay grown between navigations when the target
    # server itself is slowing down. `None` disables backoff (and the
    # circuit breaker below) entirely.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#backoff_ceiling_seconds
    backoff_ceiling_seconds: Optional[float] = 20.0
    # How long every worker pauses once the circuit breaker trips (a
    # navigation >= _SEVERE_SLOWDOWN_MULTIPLIER times the crawl's fastest).
    # Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#circuit_breaker_cooldown_seconds
    circuit_breaker_cooldown_seconds: float = 10.0
    # Outer backstop around every arun() call, independent of page_timeout_seconds
    # (which only bounds crawl4ai's OWN internal navigation timeout, once a
    # navigation actually starts). Confirmed live on austral.edu.ar: a full
    # crawl deadlocked for 12+ minutes with zero recovery - a py-spy dump of
    # the live process proved none of the workers had even reached a graph-
    # store write yet, so the stall was somewhere inside crawl4ai/Playwright
    # itself (most likely a browser/session-management lock, contested at a
    # much higher rate under two_phase_crawl's scout sweep, which removes the
    # interaction pacing that kept this from ever surfacing before) - a class
    # of hang page_timeout_seconds structurally cannot bound, since it never
    # gets the chance to start its own internal clock.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler/config.md#navigation_watchdog_seconds
    navigation_watchdog_seconds: float = 60.0
