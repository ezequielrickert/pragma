"""How much one crawl run is allowed to do before it stops and hands over.

A run stops for one of two reasons: the frontier drained (the site is done),
or a budget tripped (this slice is done, the rest stays Pending for the next
run). With every budget unset the second reason never fires and the behavior
is what it always was - "one long run" is not a mode, it is `None`.

Details: docs/dev/spiders/orchestration/mechanical_loop/budget.md#module
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CrawlBudget:
    """Caps for a single run, each independently optional.
    Details: docs/dev/spiders/orchestration/mechanical_loop/budget.md#crawlbudget
    """

    # Pages finished this run. The unit that matches how a person thinks
    # about it ("20 pages, look at the data, 20 more").
    pages: Optional[int] = None
    # Graph nodes created this run - a proxy for how heavy the store is
    # getting, which is a different question from how long the run took.
    nodes: Optional[int] = None
    # Wall clock. The only cap that still fires when a single page never
    # finishes: since d59ce99 removed the per-page ceiling, a page whose DOM
    # keeps minting components ends no page and creates no node, so `pages`
    # and `nodes` both stall while the run continues forever.
    # Details: docs/dev/spiders/orchestration/mechanical_loop/budget.md#minutes
    minutes: Optional[float] = None

    def is_unlimited(self) -> bool:
        return self.pages is None and self.nodes is None and self.minutes is None


class BudgetTracker:
    """Counts a run's work against a `CrawlBudget` and names what tripped.

    Owns its own start time so a caller cannot forget to set one, and reports
    the reason as text because the only consumer is a human reading why their
    crawl stopped early.
    Details: docs/dev/spiders/orchestration/mechanical_loop/budget.md#budgettracker
    """

    def __init__(self, budget: Optional[CrawlBudget] = None) -> None:
        self.budget = budget or CrawlBudget()
        self.pages = 0
        self.nodes = 0
        self._started_at = time.monotonic()

    def record_page(self) -> None:
        self.pages += 1

    def record_nodes(self, count: int) -> None:
        self.nodes += count

    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self._started_at) / 60.0

    def exhausted_reason(self) -> Optional[str]:
        """Which cap tripped, or `None` while there is room left.

        Checked in declaration order, so a run that trips two at once reports
        the page count - the one the operator most likely set on purpose.
        Details: docs/dev/spiders/orchestration/mechanical_loop/budget.md#exhausted_reason
        """
        limits = self.budget
        if limits.pages is not None and self.pages >= limits.pages:
            return f"page budget reached ({self.pages}/{limits.pages} pages)"
        if limits.nodes is not None and self.nodes >= limits.nodes:
            return f"node budget reached ({self.nodes}/{limits.nodes} graph nodes)"
        if limits.minutes is not None and self.elapsed_minutes() >= limits.minutes:
            return f"time budget reached ({self.elapsed_minutes():.1f}/{limits.minutes:g} minutes)"
        return None
