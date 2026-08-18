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
    # How many times requeue() will put the same clean_url key back on the
    # frontier after an interrupted pass before giving up on it for good.
    # requeue() deliberately bypasses enqueue()'s dedup guard (it has to -
    # the page it's resuming is already in that set), which also means it
    # has no cap of its own: a page that reliably trips an anti-bot block,
    # or a popular redirect destination many different interrupted passes
    # all land on and each independently requeue, would otherwise cycle
    # forever - the crawl's own "requeued" count climbing far faster than
    # "unique" and the queue growing without bound.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#max_requeue_attempts
    max_requeue_attempts: int = 3
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
    # When True, crawl_site() runs two fully separate site-wide sweeps instead
    # of PageVisitor.visit()'s usual fused scout+interact pass per page: first
    # drains the whole frontier calling only PageVisitor.scout() (discover_page
    # + the sink bookkeeping + link discovery, never a click/fill), then
    # queries the graph store for every page scout() left "Scouted" and drains
    # a fresh pass over exactly those pages calling PageVisitor.interact()
    # (which re-navigates via its own discover_page() - the tab necessarily
    # moved during the scout sweep, and a component's own path/selector
    # churns across separate discover_page() reloads, see
    # frontier.md#_navigation_trigger_identities - but skips the sink
    # bookkeeping and enqueue_links scout() already did). False (the default)
    # reproduces today's single fused-pass behavior exactly, unchanged. Not
    # named `prefetch` - that name is already Crawl4AICrawlerConfig.prefetch,
    # an unrelated crawl4ai markdown-pipeline skip.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#two_phase_crawl
    two_phase_crawl: bool = False
