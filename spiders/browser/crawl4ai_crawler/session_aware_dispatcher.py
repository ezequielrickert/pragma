"""Fixes crawl4ai's `MemoryAdaptiveDispatcher` silently dropping the
`session_id` it means to give each concurrent fetch.
Details: docs/dev/spiders/browser/crawl4ai_crawler/session_aware_dispatcher.md#module
"""
from __future__ import annotations

from typing import List, Union

from crawl4ai import CrawlerRunConfig
from crawl4ai.async_dispatcher import CrawlerTaskResult, MemoryAdaptiveDispatcher


class SessionAwareDispatcher(MemoryAdaptiveDispatcher):
    """`MemoryAdaptiveDispatcher.crawl_url` passes `session_id=task_id` to
    `AsyncWebCrawler.arun()` as a bare keyword argument, which `arun()`
    never reads (it only ever consults `config.session_id` -
    `async_webcrawler.py:210,294,392,477`) - so every concurrent fetch a
    batch or stream runs shares whatever `session_id` the one `config`
    handed to the dispatcher already carried (`None`, falling back to
    `"default"`). This class fixes it at the one place both `run_urls`
    (batch) and `run_urls_stream` share: `crawl_url` itself resolves
    `config.session_id` before `arun()` ever sees it, on `crawl4ai`'s own
    per-URL `selected_config`, so `arun()` reads a distinct, correct
    session_id off the config regardless of the kwarg it drops.

    Deliberately does not reproduce `MemoryAdaptiveDispatcher.crawl_url`'s
    ~140 lines (memory-pressure requeueing, rate limiting, monitor
    updates) to change one thing - `select_config`'s result already
    carries every field this dispatcher cares about, so cloning it with
    the right `session_id` and handing off to `super().crawl_url` keeps
    this override tied to crawl4ai's own resolution behavior instead of a
    second, driftable copy of it.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/session_aware_dispatcher.md#sessionawaredispatcher
    """

    async def crawl_url(
        self,
        url: str,
        config: Union[CrawlerRunConfig, List[CrawlerRunConfig]],
        task_id: str,
        retry_count: int = 0,
    ) -> CrawlerTaskResult:
        """Same contract as `MemoryAdaptiveDispatcher.crawl_url` - resolves
        `config` down to the one `CrawlerRunConfig` `url` matches (crawl4ai's
        own `select_config`), clones it with `session_id=task_id` baked in,
        then defers everything else to the base implementation, which
        re-resolves that already-single config as a no-op (`select_config`
        returns a lone `CrawlerRunConfig` unchanged) before using it.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/session_aware_dispatcher.md#crawl_url
        """
        selected_config = self.select_config(url, config)
        if selected_config is not None:
            selected_config = selected_config.clone(session_id=task_id)
        return await super().crawl_url(url, selected_config, task_id, retry_count)
