"""Reader-writer coordination between in-flight browser operations and
session recycling, both sharing one crawl4ai browser context.
Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#module
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class SessionRecycleGate:
    """Every `arun()`-based operation (navigation, interaction) is a
    *reader* - many run concurrently, exactly as they already do.
    `close_session` (which can tear down the *shared* browser context, not
    just its own page, if crawl4ai judges it the context's last active
    page - see `docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#close_session`)
    is a *writer* - it needs every reader to finish first, and no new
    reader may start while a writer is pending or running, or a recycle
    could tear the context down out from under a page another worker is
    actively navigating. Confirmed live on austral.edu.ar as the
    best-supported explanation for a third deadlock, after `arun()` and
    `close_session` were each independently bounded and neither one alone
    explained it.

    **Writers never wait on each other** - only on readers. An earlier
    version serialized writers through a single `asyncio.Lock`, reasoned
    as safe because recycling is infrequent; that reasoning broke down
    live on austral.edu.ar the moment the target started straining (a
    `TargetLoadThrottle` circuit-breaker trip, navigations running 10s+):
    every worker progresses through pages at roughly the same degraded
    pace, so several independently hit `session_recycle_after` close
    together, and each one's own reader-drain wait (bounded by
    `navigation_watchdog_seconds`) queued fully behind the last, turning
    an intended ~60s bound into up to `page_concurrency` x that. Two
    writers recycling *different* sessions never conflict with each
    other in the first place - the one shared thing they could race on
    (a shared context's refcount) is already protected by crawl4ai's own
    internal lock inside `kill_session`, not something this gate needs
    to duplicate.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#sessionrecyclegate
    """

    def __init__(self) -> None:
        self._active_readers = 0
        self._active_writers = 0
        self._condition = asyncio.Condition()

    @asynccontextmanager
    async def reader(self) -> AsyncIterator[None]:
        """Hold for the duration of one `arun()`-based operation.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#reader
        """
        async with self._condition:
            while self._active_writers > 0:
                await self._condition.wait()
            self._active_readers += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active_readers -= 1
                if self._active_readers == 0:
                    self._condition.notify_all()

    @asynccontextmanager
    async def writer(self, drain_timeout_seconds: float) -> AsyncIterator[None]:
        """Hold for the duration of one `close_session` call. Waits up to
        `drain_timeout_seconds` for every currently-active reader to
        finish - bounded, not indefinite, since every reader is itself
        bounded by `navigation_watchdog_seconds` (`_run_with_watchdog`'s
        own guarantee), so passing that same value here means this can
        never wait longer than a single hung reader's own recovery already
        takes. Proceeds anyway past the deadline (with a warning) rather
        than let a bug in some future, differently-bounded reader stall
        recycling forever - the same "give up and proceed" discipline
        `WorkerPacing.wait_for_memory_headroom` already established for
        its own bounded wait.

        Runs concurrently with any other writer already in progress -
        see the class's own docstring for why that's safe and why an
        earlier version's full serialization was a real bug, not just
        unnecessary caution.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#writer
        """
        async with self._condition:
            self._active_writers += 1
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(lambda: self._active_readers == 0),
                    timeout=drain_timeout_seconds,
                )
            except asyncio.TimeoutError:
                print(
                    f"Warning: session recycle proceeding after {drain_timeout_seconds:.0f}s "
                    f"still waiting on {self._active_readers} in-flight browser operation(s)."
                )
        try:
            yield
        finally:
            async with self._condition:
                self._active_writers -= 1
                if self._active_writers == 0:
                    self._condition.notify_all()
