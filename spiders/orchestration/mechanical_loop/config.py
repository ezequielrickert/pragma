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
    # When True, crawl_site() runs the scout sweep only and returns - no
    # interact phase, in this process or any later one triggered by it.
    # Pages land in the graph store "Scouted" - `pragma static`'s own
    # crawl mode - so a later, separate `pragma dynamic` invocation can
    # pick them up via `get_scouted()`.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#scout_only
    scout_only: bool = False
    # When True, crawl_site() skips discovery entirely and runs only
    # PageVisitor.interact() over whatever a previous, separate run already
    # left "Scouted" (`get_scouted()`) - the mode `pragma dynamic` runs
    # under when it's resuming a prior `pragma static` run instead of
    # rediscovering the site itself. `start_url` itself is never enqueued
    # for scouting here - there is nothing to scout in this process, only
    # to interact with.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#interact_only
    interact_only: bool = False
    # `analysis/family_sampling.py::FamilySampler`, or `None` to interact
    # with every eligible component as usual. Consulted by `PageVisitor`
    # once per component, before any click/fill - the mechanism
    # `pragma dynamic` uses to skip components already known (via
    # `pragma cluster`'s output) to belong to a repeating family once
    # enough instances of that family have already been sampled.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#family_sampler
    family_sampler: Optional[Any] = None
    # `analysis/exact_reuse_index.py::ExactReuseIndex`, or `None` to skip
    # the exact-tier interact-once check entirely. Consulted by
    # `PageVisitor` before `family_sampler` on every component - a
    # canonical `Component` reused across pages is interacted with once,
    # ever, per run, with its outcome inferred onto every other page it
    # renders on, rather than sampled like a family.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/config.md#exact_reuse_index
    exact_reuse_index: Optional[Any] = None
