"""A fixed set of independent Crawl4AICrawler browser processes, assigned to
sessions by current load rather than a fixed rule.
Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#module
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from ..core.interfaces import PageState
from .crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig
from .target_load_throttle import TargetLoadThrottle


class Crawl4AICrawlerPool:
    """`pool_size` real Chromium processes, each its own `Crawl4AICrawler` -
    not `page_concurrency` tabs sharing one process. A session_id is bound to
    whichever pool member currently has the fewest in-flight calls at the
    moment it's first seen (or reassigned after a recycle) - not a fixed
    rule - so two workers that happen to keep drawing heavy pages don't stay
    stuck piling load onto the same browser for the rest of the crawl.
    Binding still holds for a session's whole life between recycles, so
    within-page interaction reuse (fetch once, interact many times) is
    unaffected - only cross-visit, cross-recycle placement is dynamic.

    Duck-type compatible with `Crawl4AICrawler` (discover_page/click/fill/
    resync/close_session/target_slowdown_ratio) - callers that already hold
    a `Crawl4AICrawler` need no changes, matching this project's existing
    no-formal-Protocol convention.
    Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#crawl4aicrawlerpool
    """

    def __init__(self, config: Optional[Crawl4AICrawlerConfig] = None, pool_size: int = 1) -> None:
        config = config or Crawl4AICrawlerConfig()
        # One throttle shared by every pool member - the target server can't
        # tell how many of our browser processes are hitting it, so backoff/
        # circuit-breaker state must be pooled too, not per-instance.
        # Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#__init__-shared-throttle
        self._throttle = TargetLoadThrottle(config.backoff_ceiling_seconds, config.circuit_breaker_cooldown_seconds)
        self._crawlers: List[Crawl4AICrawler] = [
            Crawl4AICrawler(config, throttle=self._throttle) for _ in range(max(1, pool_size))
        ]
        self._owner_by_session: Dict[str, Crawl4AICrawler] = {}
        # In-flight call count per pool member - the real-time "how busy is
        # this browser right now" signal a session gets placed against.
        # Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#__init__-active-calls
        self._active_calls: Dict[int, int] = {id(crawler): 0 for crawler in self._crawlers}
        self._tie_break_cursor = 0

    async def __aenter__(self) -> "Crawl4AICrawlerPool":
        await asyncio.gather(*(crawler.__aenter__() for crawler in self._crawlers))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await asyncio.gather(*(crawler.__aexit__(exc_type, exc, tb) for crawler in self._crawlers), return_exceptions=True)

    def _least_loaded_crawler(self) -> Crawl4AICrawler:
        """Whichever pool member has the fewest in-flight calls right now;
        ties broken round-robin so an idle pool doesn't always favor the
        first instance. Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#_least_loaded_crawler
        """
        start = self._tie_break_cursor
        self._tie_break_cursor = (start + 1) % len(self._crawlers)
        ordered = self._crawlers[start:] + self._crawlers[:start]
        return min(ordered, key=lambda crawler: self._active_calls[id(crawler)])

    def _owner_for(self, session_id: str) -> Crawl4AICrawler:
        """The pool member `session_id` is bound to until its next recycle.
        Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#_owner_for
        """
        owner = self._owner_by_session.get(session_id)
        if owner is None:
            owner = self._least_loaded_crawler()
            self._owner_by_session[session_id] = owner
        return owner

    async def _call(self, session_id: str, coro_factory) -> PageState:
        """Route one call to `session_id`'s owner, counting it as in-flight
        for the load-balancing decision above for the call's whole duration.
        Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#_call
        """
        owner = self._owner_for(session_id)
        self._active_calls[id(owner)] += 1
        try:
            return await coro_factory(owner)
        finally:
            self._active_calls[id(owner)] -= 1

    @property
    def target_slowdown_ratio(self) -> float:
        """Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#target_slowdown_ratio"""
        return self._throttle.target_slowdown_ratio

    @property
    def consecutive_trips(self) -> int:
        """Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#consecutive_trips"""
        return self._throttle.consecutive_trips

    async def discover_page(self, url: str, session_id: Optional[str] = None) -> PageState:
        session_id = session_id or url
        return await self._call(session_id, lambda owner: owner.discover_page(url, session_id=session_id))

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        return await self._call(session_id, lambda owner: owner.click(url, session_id, selector))

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        return await self._call(session_id, lambda owner: owner.fill(url, session_id, selector, value))

    async def resync(self, url: str, session_id: str) -> PageState:
        return await self._call(session_id, lambda owner: owner.resync(url, session_id))

    async def close_session(self, session_id: str) -> None:
        """Recycle `session_id`'s tab and release its pool-member binding -
        its next visit gets placed against whichever browser is least loaded
        *then*, not forced back onto the one it happened to start on.
        Details: docs/dev/crawlers/crawl4ai_crawler_pool.md#close_session
        """
        owner = self._owner_by_session.pop(session_id, None)
        if owner is not None:
            await owner.close_session(session_id)
