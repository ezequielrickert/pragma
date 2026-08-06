"""Owns the single, persistent `PlaywrightScraper` for this server process's lifetime.

Split out from `dynamic.py` so both the router (per-request calls) and `app.py`'s shutdown
handler (final cleanup) can share the same singleton/executor without a circular import.

Playwright's sync API refuses to run inside a thread that already has an asyncio event loop
running - uvicorn's request-handling threads do. FastAPI's default behavior for sync `def`
endpoints (`run_in_threadpool`) doesn't help either: that pulls from a pool of *interchangeable*
worker threads, and Playwright's browser/page objects are bound to whichever single OS thread
created them. A dedicated `ThreadPoolExecutor(max_workers=1)` is required so every Playwright call,
across the whole server process's lifetime, lands on the same thread.
"""
from __future__ import annotations

import asyncio
import atexit
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from ..scrapers.playwright_scraper import PlaywrightScraper

_scraper: Optional[PlaywrightScraper] = None
_executor = ThreadPoolExecutor(max_workers=1)


def _get_scraper() -> PlaywrightScraper:
    """Lazily create the process-lifetime PlaywrightScraper singleton.

    Only ever called from `_executor`'s single worker thread. `headless`/`wait_seconds`
    are this server's own startup config (env vars), not threaded through per-request -
    see ARCHITECTURE.md's "Module 3" section on why this differs from a per-run setting.
    """
    global _scraper
    if _scraper is None:
        headless = os.getenv("PRAGMA_API_HEADLESS", "True") == "True"
        wait_seconds = float(os.getenv("PRAGMA_API_WAIT_SECONDS", "15.0"))
        _scraper = PlaywrightScraper(headless=headless, wait_seconds=wait_seconds)
    return _scraper


async def run(func: Callable[[PlaywrightScraper], Any]) -> Any:
    """Run `func(scraper)` on the dedicated worker thread and return its result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, func, _get_scraper())


def close_scraper() -> None:
    """Best-effort browser shutdown when the server process exits.

    Submitted to `_executor` rather than called directly: the browser/page were created on
    that worker thread, and Playwright's sync API objects must be torn down from the same
    thread that created them.
    """
    global _scraper
    if _scraper is not None:
        try:
            _executor.submit(_scraper.close).result(timeout=10)
        except RuntimeError:
            # The interpreter can tear down ThreadPoolExecutor's own worker threads (via its
            # own atexit hook) before this handler runs, in which case there's no thread left
            # to close the browser from cleanly - not worth failing shutdown over.
            pass
        _scraper = None


atexit.register(close_scraper)
