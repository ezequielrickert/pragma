"""Every tuning knob MechanicalCrawler accepts beyond crawler/tracker.
Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from ...content.fill_values import default_placeholder_fill_value
from ..graph_sink import GraphStoreSink
from .budget import CrawlBudget


@dataclass
class MechanicalCrawlerConfig:
    """Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#mechanicalcrawlerconfig"""

    fill_value_fn: Callable[[Dict[str, Any], str], Awaitable[str]] = default_placeholder_fill_value
    max_pages: Optional[int] = None
    # What this run is allowed to do before stopping and leaving the rest
    # Pending. All-unset (the default) means "until the frontier drains",
    # which is what every run did before this existed.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#budget
    budget: Optional[CrawlBudget] = None
    sink: Optional[GraphStoreSink] = None
    max_visits_per_route_shape: int = 1
    # See PragmaConfig.page_concurrency for why this default isn't 1 anymore.
    page_concurrency: int = 4
    state_transition_overlap_threshold: float = 0.5
    base_url: Optional[str] = None
    allow_subdomains: bool = False
    # Visits per worker tab before it's closed and rebuilt from scratch.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#session_recycle_after
    session_recycle_after: Optional[int] = 15
    # System-memory-used percent above which a worker pauses picking up its
    # next page - what makes raising page_concurrency safe rather than just
    # a faster way to reproduce the same OOM. `None` disables the check.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#memory_ceiling_percent
    memory_ceiling_percent: Optional[float] = 85.0
    # Effective worker count never drops below this even under severe target
    # strain - see worker_pacing.py's own effective_concurrency.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#min_page_concurrency
    min_page_concurrency: int = 1
    # crawler.target_slowdown_ratio range over which effective concurrency
    # linearly tapers from page_concurrency down to min_page_concurrency -
    # below the start ratio, full concurrency; at/above the end ratio, the
    # floor. Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#concurrency_taper
    concurrency_taper_start_ratio: float = 2.0
    concurrency_taper_end_ratio: float = 4.0
