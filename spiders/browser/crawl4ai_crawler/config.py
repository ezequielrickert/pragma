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
