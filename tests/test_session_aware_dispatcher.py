"""Regression test for SessionAwareDispatcher
(spiders/browser/crawl4ai_crawler/session_aware_dispatcher.py) - fixes
MemoryAdaptiveDispatcher's dropped session_id, the bug where every
concurrent fetch in a dispatcher batch/stream shared one config's
session_id (`None`/"default") because AsyncWebCrawler.arun() never reads
the bare `session_id=` kwarg the base dispatcher passes it, only
`config.session_id`. This is the exact scenario the original bug
corrupted: several concurrent fetches through one shared CrawlerRunConfig,
each needing a *distinct* session_id in the result crawl4ai's own
arun() actually saw.
"""
import asyncio

from crawl4ai import CrawlerRunConfig
from crawl4ai.models import CrawlResult

from spiders.browser.crawl4ai_crawler import SessionAwareDispatcher


class _RecordingCrawler:
    """Stands in for AsyncWebCrawler: records the session_id each arun()
    call actually received on its config (what the real AsyncWebCrawler
    reads), not the stray session_id= kwarg the dispatcher also passes
    (what the real AsyncWebCrawler silently drops) - mirroring
    async_webcrawler.py's own behavior closely enough to catch the bug
    without needing a real browser."""

    def __init__(self) -> None:
        self.seen_session_ids: list[str] = []

    async def arun(self, url: str, config: CrawlerRunConfig, **_ignored_kwargs) -> CrawlResult:
        # Overlap several calls before returning, so a shared/racing
        # session_id would show up as a duplicate in seen_session_ids.
        await asyncio.sleep(0.05)
        self.seen_session_ids.append(config.session_id)
        return CrawlResult(url=url, html="", success=True)


def test_concurrent_fetches_get_distinct_session_ids():
    """Several URLs sharing one CrawlerRunConfig, dispatched through
    run_urls_stream's real concurrency path, must each reach arun() with
    a different session_id - the exact case MemoryAdaptiveDispatcher's
    dropped kwarg silently broke."""
    crawler = _RecordingCrawler()
    dispatcher = SessionAwareDispatcher(max_session_permit=5)
    shared_config = CrawlerRunConfig()
    urls = [f"http://example.test/page-{n}" for n in range(5)]

    async def run():
        results = []
        async for task_result in dispatcher.run_urls_stream(urls, crawler, shared_config):
            results.append(task_result)
        return results

    results = asyncio.run(run())

    assert len(results) == len(urls)
    assert all(task_result.result.success for task_result in results)
    assert len(set(crawler.seen_session_ids)) == len(urls)
    assert shared_config.session_id not in crawler.seen_session_ids


def test_no_matching_config_still_fails_cleanly():
    """A URL matching none of a config list must still fail the same way
    the base dispatcher does - the None-selected-config path must survive
    this override's .clone() call unchanged."""
    crawler = _RecordingCrawler()
    dispatcher = SessionAwareDispatcher(max_session_permit=5)
    non_matching_config = CrawlerRunConfig(url_matcher=lambda url: False)

    async def run():
        return await dispatcher.crawl_url(
            "http://example.test/unmatched", [non_matching_config], task_id="task-1"
        )

    task_result = asyncio.run(run())

    assert task_result.result.success is False
    assert crawler.seen_session_ids == []
