"""Why one crawl session ends early, and the budgets that decide it.
Details: docs/dev/crawlers/crawl_stopper.md#module
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StopReason(Enum):
    """What ended a session before its frontier drained. `None` (no reason
    at all) is the separate, healthy case: the frontier ran dry.
    Details: docs/dev/crawlers/crawl_stopper.md#stopreason
    """

    RATE_LIMITED = "rate-limited"
    PAGE_BUDGET = "page-budget"
    TIME_BUDGET = "time-budget"
    INTERRUPT = "interrupt"


@dataclass
class SessionBudget:
    """How much of a crawl one session is allowed to do before stopping so
    the rest can be resumed later. Every field off by default - an
    unbudgeted session behaves exactly as it did before this existed.
    Details: docs/dev/crawlers/crawl_stopper.md#sessionbudget
    """

    # Pages this session may visit. Distinct from PragmaConfig.max_pages,
    # which caps the crawl across every session that ever resumed it.
    # Details: docs/dev/crawlers/crawl_stopper.md#stop_after_pages
    stop_after_pages: Optional[int] = None
    # Wall-clock seconds from `begin()`, enforced by a timer rather than by
    # polling, so it fires even while every worker sits idle on the frontier.
    # Details: docs/dev/crawlers/crawl_stopper.md#stop_after_seconds
    stop_after_seconds: Optional[float] = None
    # Consecutive TargetLoadThrottle circuit-breaker trips that end the
    # session. `None` or 0 disables it: the crawl then keeps backing off and
    # tapering concurrency forever instead of stopping to be resumed. 0 is
    # accepted as well as `None` because a config layer that treats `None`
    # as "no value given" cannot express "off" any other way.
    # Details: docs/dev/crawlers/crawl_stopper.md#stop_after_rate_limit_trips
    stop_after_rate_limit_trips: Optional[int] = 3


class CrawlStopper:
    """Decides whether this session should end early, and remembers why.
    Knows nothing about URLs, browsers or graphs - `MechanicalCrawler`
    reports facts to it and consults it, and everything it learns about
    the target reaches it as a plain number.
    Details: docs/dev/crawlers/crawl_stopper.md#crawlstopper
    """

    def __init__(self, budget: Optional[SessionBudget] = None) -> None:
        self.budget = budget or SessionBudget()
        self._stopped = asyncio.Event()
        self._reason: Optional[StopReason] = None
        self._pages_this_session = 0
        self._deadline_task: Optional["asyncio.Task[None]"] = None

    @property
    def reason(self) -> Optional[StopReason]:
        """Why the session stopped, or `None` if it was never asked to.
        Details: docs/dev/crawlers/crawl_stopper.md#reason
        """
        return self._reason

    def begin(self) -> None:
        """Start the wall-clock budget, if there is one. Called once the
        crawl is genuinely underway, so browser startup doesn't eat into a
        session's time budget. Requires a running event loop.
        Details: docs/dev/crawlers/crawl_stopper.md#begin
        """
        if self.budget.stop_after_seconds is None:
            return
        self._deadline_task = asyncio.create_task(self._stop_at_deadline())

    def close(self) -> None:
        """Cancel the wall-clock timer. Safe to call when `begin()` never
        ran or the deadline already fired.
        Details: docs/dev/crawlers/crawl_stopper.md#close
        """
        if self._deadline_task is not None:
            self._deadline_task.cancel()
            self._deadline_task = None

    async def _stop_at_deadline(self) -> None:
        """Sleep out the time budget, then end the session.
        Details: docs/dev/crawlers/crawl_stopper.md#_stop_at_deadline
        """
        await asyncio.sleep(self.budget.stop_after_seconds or 0)
        self.request_stop(StopReason.TIME_BUDGET)

    def request_stop(self, reason: StopReason) -> None:
        """End the session, recording `reason`. Idempotent, and the first
        reason wins - a later trigger firing during the stop's own grace
        period shouldn't rewrite what actually stopped the crawl.
        Details: docs/dev/crawlers/crawl_stopper.md#request_stop
        """
        if self._stopped.is_set():
            return
        self._reason = reason
        self._stopped.set()
        print(f"Stopping this crawl session early ({reason.value}); resume it with --no-fresh.")

    def should_stop(self) -> bool:
        """Whether workers should stop picking up new pages.
        Details: docs/dev/crawlers/crawl_stopper.md#should_stop
        """
        return self._stopped.is_set()

    async def wait(self) -> None:
        """Block until something ends the session.
        Details: docs/dev/crawlers/crawl_stopper.md#wait
        """
        await self._stopped.wait()

    def record_page_visited(self) -> None:
        """Count one finished page against the session's page budget,
        ending the session once it's spent.
        Details: docs/dev/crawlers/crawl_stopper.md#record_page_visited
        """
        self._pages_this_session += 1
        limit = self.budget.stop_after_pages
        if limit is not None and self._pages_this_session >= limit:
            self.request_stop(StopReason.PAGE_BUDGET)

    def record_rate_limit_trips(self, consecutive_trips: int) -> None:
        """React to how many times in a row the target has tripped the
        circuit breaker. Past the budget, backing off further is just a
        slower way to keep hitting a target that's already refusing load -
        stopping leaves the rest of the frontier Pending for a later run.
        Details: docs/dev/crawlers/crawl_stopper.md#record_rate_limit_trips
        """
        limit = self.budget.stop_after_rate_limit_trips
        if limit and consecutive_trips >= limit:
            self.request_stop(StopReason.RATE_LIMITED)
