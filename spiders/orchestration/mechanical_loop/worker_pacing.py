"""How many workers should be actively fetching right now - a memory-
pressure gate plus a target-health-based concurrency taper, independent
of which URLs exist or which worker is currently running.
Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#module
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import psutil

from .config import MechanicalCrawlerConfig

if TYPE_CHECKING:
    from ...browser.crawl4ai_crawler import Crawl4AICrawler

# wait_for_memory_headroom's poll interval while blocked.
# Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#_memory_check_interval_seconds
_MEMORY_CHECK_INTERVAL_SECONDS = 2.0

# Give up waiting and proceed anyway past this many seconds under the
# ceiling, so a machine whose memory pressure has nothing to do with this
# crawl (or stays permanently loaded) can't stall it forever.
# Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#_memory_wait_timeout_seconds
_MEMORY_WAIT_TIMEOUT_SECONDS = 300.0

# wait_for_capacity's poll interval while a worker is over budget.
# Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#_target_health_check_interval_seconds
_TARGET_HEALTH_CHECK_INTERVAL_SECONDS = 1.0


class WorkerPacing:
    """Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#workerpacing"""

    def __init__(self, crawler: "Crawl4AICrawler", config: MechanicalCrawlerConfig) -> None:
        self.crawler = crawler
        self.page_concurrency = max(1, config.page_concurrency)
        self.min_page_concurrency = max(1, min(config.min_page_concurrency, self.page_concurrency))
        self.memory_ceiling_percent = config.memory_ceiling_percent
        self.concurrency_taper_start_ratio = config.concurrency_taper_start_ratio
        self.concurrency_taper_end_ratio = config.concurrency_taper_end_ratio

    async def wait_for_memory_headroom(self) -> None:
        """Block this worker from picking up its next page while system
        memory is over `memory_ceiling_percent` used. A crawl with several
        concurrent Chromium tabs can genuinely run the machine out of memory;
        this is what lets `page_concurrency` be raised without just hitting
        that ceiling faster. Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#wait_for_memory_headroom
        """
        if self.memory_ceiling_percent is None:
            return
        waited_seconds = 0.0
        while psutil.virtual_memory().percent >= self.memory_ceiling_percent:
            if waited_seconds >= _MEMORY_WAIT_TIMEOUT_SECONDS:
                print(
                    f"Warning: system memory still >= {self.memory_ceiling_percent}% used after "
                    f"{_MEMORY_WAIT_TIMEOUT_SECONDS:.0f}s - proceeding anyway rather than stall forever."
                )
                return
            await asyncio.sleep(_MEMORY_CHECK_INTERVAL_SECONDS)
            waited_seconds += _MEMORY_CHECK_INTERVAL_SECONDS

    def effective_concurrency(self) -> int:
        """How many workers should be actively fetching right now, tapered
        down from `page_concurrency` toward `min_page_concurrency` as
        `crawler.target_slowdown_ratio` worsens - fewer simultaneous
        in-flight requests against a target that's already straining, not
        just slower per-request pacing (that's `Crawl4AICrawler`'s own
        backoff). Reads a plain attribute `Crawl4AICrawler` updates every
        navigation; missing entirely (e.g. a fake crawler in a test) reads
        as "healthy", not as degraded.
        Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#effective_concurrency
        """
        ratio = getattr(self.crawler, "target_slowdown_ratio", 1.0)
        if ratio <= self.concurrency_taper_start_ratio:
            return self.page_concurrency
        if ratio >= self.concurrency_taper_end_ratio:
            return self.min_page_concurrency
        taper_span = self.concurrency_taper_end_ratio - self.concurrency_taper_start_ratio
        fraction_degraded = (ratio - self.concurrency_taper_start_ratio) / taper_span
        reduction = round(fraction_degraded * (self.page_concurrency - self.min_page_concurrency))
        return max(self.min_page_concurrency, self.page_concurrency - reduction)

    async def wait_for_capacity(self, worker_id: int) -> None:
        """Block this worker while its id is outside the currently allowed
        concurrency budget (see `effective_concurrency`). `min_page_concurrency`
        defaults to 1, so worker 0 always qualifies and the crawl can never
        fully stall here - only higher-numbered workers ever wait, and only
        for as long as the target stays degraded.
        Details: docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#wait_for_capacity
        """
        while worker_id >= self.effective_concurrency():
            await asyncio.sleep(_TARGET_HEALTH_CHECK_INTERVAL_SECONDS)
