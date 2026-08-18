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
    Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#sessionrecyclegate
    """

    def __init__(self) -> None:
        self._active_readers = 0
        self._writer_pending = False
        self._condition = asyncio.Condition()
        # Serializes writers among themselves - recycling is infrequent
        # (every session_recycle_after visits per worker), so contention
        # between two concurrent recycles is rare enough that fully
        # serializing them is simpler than a second reference count.
        self._writer_lock = asyncio.Lock()

    @asynccontextmanager
    async def reader(self) -> AsyncIterator[None]:
        """Hold for the duration of one `arun()`-based operation.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#reader
        """
        async with self._condition:
            while self._writer_pending:
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
        Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#writer
        """
        async with self._writer_lock:
            async with self._condition:
                self._writer_pending = True
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
                    self._writer_pending = False
                    self._condition.notify_all()
