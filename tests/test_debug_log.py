"""Regression coverage for CrawlDebugLog.save_page_markdown's history file.

See wiki/graph-based-crawl-tracking.md's "separate the live snapshot from the
append-only audit trail" principle. Confirmed live on austral.edu.ar: a single
page visit calls `save_page_markdown` once per interaction within a session
(discover_page/_interact/resync all call it - see Crawl4AICrawler._save_markdown),
not just once per page. A snapshot that captured real discovered content
(e.g. a component's revealed items) was silently lost the moment a *later*,
possibly unrelated interaction in the same session overwrote a live-snapshot
file with different content - no trace it ever existed. That overwrite-only
file was later dropped entirely; only the history file remains.

Writes are queued and drained by a background task (see debug_log.py's
`CrawlDebugLog`), not written inline - `close()` is `async` and must be
awaited before reading files back, so every test here goes through
`asyncio.run()`, matching test_crawl4ai_crawler.py's convention (no
pytest-asyncio dependency for a suite this small).
"""
import asyncio
import os

from src.crawlers.debug_log import CrawlDebugLog


def test_save_page_markdown_preserves_earlier_snapshots_in_history_file(tmp_path):
    async def run() -> None:
        log = CrawlDebugLog(str(tmp_path), site="example.com")
        try:
            url = "https://example.com/widget"

            # First snapshot: a component's items got discovered.
            log.save_page_markdown(url, "# Widget\n\n- item one\n- item two\n- item three")

            # A later, unrelated interaction in the same session re-saves the
            # same page's markdown - a real, independent snapshot in its own
            # right, not a correction of the first one.
            log.save_page_markdown(url, "# Widget\n\n(items collapsed)")
        finally:
            await log.close()

    asyncio.run(run())

    history_path = os.path.join(str(tmp_path), "pages", "example.com_widget.history.md")
    assert os.path.exists(history_path)

    history_content = open(history_path, encoding="utf-8").read()

    # History file must retain BOTH snapshots, in order - this is what fails
    # without the fix (an overwrite-only save loses the first one).
    assert "item one" in history_content
    assert "collapsed" in history_content
    assert history_content.index("item one") < history_content.index("collapsed")


def test_save_page_markdown_returns_before_write_completes(tmp_path):
    """Enqueuing a write must not block the caller on the disk I/O itself."""

    async def run() -> None:
        log = CrawlDebugLog(str(tmp_path), site="example.com")
        try:
            path = log.save_page_markdown("https://example.com/", "# Home")
            # The path is a deterministic string join - available immediately,
            # regardless of whether the background writer has run yet.
            assert path.endswith("example.com_.history.md")
        finally:
            await log.close()

    asyncio.run(run())


def test_log_hook_and_save_page_markdown_land_in_enqueue_order(tmp_path):
    async def run() -> None:
        log = CrawlDebugLog(str(tmp_path), site="example.com")
        try:
            log.log_hook("before_goto", url="https://example.com/")
            log.save_page_markdown("https://example.com/", "# Home")
            log.log_hook("after_goto", url="https://example.com/")
        finally:
            await log.close()

    asyncio.run(run())

    debug_content = open(os.path.join(str(tmp_path), "debug.md"), encoding="utf-8").read()
    assert debug_content.index("`before_goto`") < debug_content.index("page_markdown_saved")
    assert debug_content.index("page_markdown_saved") < debug_content.index("`after_goto`")
