"""Regression coverage for `CrawlEngineCore`'s worker-session lifecycle -
one stable browser tab per worker, capped at `page_concurrency`, recycled
every `session_recycle_after` visits so a long crawl doesn't accumulate
JS heap/listeners for the whole run (confirmed live on austral.edu.ar: a
tab kept navigating through 50 real pages without ever closing grew from
~9MB/~90 JS event listeners to ~700MB/~11000 listeners, with V8's own
garbage-collection pauses landing squarely on the slowest FETCH timings
observed).

Relocated from `tests/test_mechanical_loop.py` (retired with the Legacy
Engine, issue #242) onto `CrawlEngineCore` - `_recycle_session_if_due` was
ported into it unchanged from `MechanicalCrawler`'s own (its own docstring
says so), so this file's coverage carries over one for one. The old
file's other tests (requeue, return-to-origin, stale-selector resync,
silent-navigation detection, worker-pacing tapering) covered navigation-
recovery/pacing machinery issue #240/#241 deliberately dropped rather than
ported, so they have no equivalent here.
"""
import asyncio
from typing import Any, Dict, List, Optional

from core.interfaces import PageState
from spiders.orchestration.engine_core import CrawlEngineCore, EngineCoreConfig


def _component(path: str, text: str, tag: str = "button") -> Dict[str, Any]:
    return {
        "tag": tag, "text": text, "path": path, "role": "", "form": "",
        "name": "", "input_type": "", "visible": True,
    }


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaDeepCrawlStrategy.link_discovery` to work against."""

    def __init__(self, url: str, links: Optional[List[Dict[str, str]]] = None) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": links or [], "external": []}
        self.metadata: Dict[str, Any] = {}


class _FakeSessionRecordingCrawler:
    """A flat fan-out from one root: `n_pages` leaf pages, each with a
    single non-navigating "item" component. Records the `session_id` every
    `discover_page_with_result` call ran under, to prove distinct browser
    tabs stay capped at `page_concurrency` instead of growing by one per
    page (confirmed live on austral.edu.ar: crawl4ai's own [FETCH] timer
    climbed from ~1s to ~30-40s over one run as a new tab piled up per
    page, with nothing ever closing them)."""

    def __init__(self, n_pages: int) -> None:
        self.root_url = "http://fixture.example/root"
        self.leaf_urls = [f"http://fixture.example/leaf{i}" for i in range(n_pages)]
        self.session_ids_seen: List[str] = []

    async def discover_page_with_result(self, url: str, session_id: Optional[str] = None):
        await asyncio.sleep(0)  # yield control - lets other workers interleave, like a real await would
        self.session_ids_seen.append(session_id)
        if url == self.root_url:
            links = [{"href": leaf} for leaf in self.leaf_urls]
            return PageState(url=self.root_url, links=[]), _FakeResult(self.root_url, links)
        state = PageState(url=url, components=[_component("body > button#item", "Item")])
        return state, _FakeResult(url)

    async def click(self, url: str, session_id: str, path: str) -> PageState:
        # No-op click: page settles with the same single item, nothing new revealed.
        return PageState(url=url, components=[_component("body > button#item", "Item")])


def test_session_count_stays_capped_at_page_concurrency_not_one_per_page():
    """Visiting many pages sequentially (page_concurrency=1) must reuse one
    browser tab throughout, not open a fresh one per page."""
    fake = _FakeSessionRecordingCrawler(n_pages=5)
    engine = CrawlEngineCore(fake, config=EngineCoreConfig(page_concurrency=1))
    asyncio.run(engine.run(fake.root_url))

    assert len(set(fake.session_ids_seen)) == 1


def test_session_count_scales_with_concurrency_not_page_count():
    """Two concurrent workers visiting many pages must still only ever use
    two distinct browser tabs between them, one per worker."""
    fake = _FakeSessionRecordingCrawler(n_pages=8)
    engine = CrawlEngineCore(fake, config=EngineCoreConfig(page_concurrency=2))
    asyncio.run(engine.run(fake.root_url))

    assert len(set(fake.session_ids_seen)) == 2


class _FakeSessionRecyclingCrawler(_FakeSessionRecordingCrawler):
    """Same flat fan-out as `_FakeSessionRecordingCrawler`, plus a
    `close_session` that records every call, to prove a long-lived worker
    tab gets closed and rebuilt every `session_recycle_after` visits
    instead of accumulating state for the whole crawl."""

    def __init__(self, n_pages: int) -> None:
        super().__init__(n_pages)
        self.closed_session_ids: List[str] = []

    async def close_session(self, session_id: str) -> None:
        self.closed_session_ids.append(session_id)


def test_session_recycled_every_configured_number_of_visits():
    fake = _FakeSessionRecyclingCrawler(n_pages=8)
    engine = CrawlEngineCore(fake, config=EngineCoreConfig(page_concurrency=1, session_recycle_after=3))
    asyncio.run(engine.run(fake.root_url))

    # 1 root + 8 leaves = 9 visits, recycled every 3rd -> exactly 3 closes.
    assert len(fake.closed_session_ids) == 3
    assert fake.closed_session_ids == ["worker-0"] * 3


class _FakeSessionRecycleFailsCrawler(_FakeSessionRecordingCrawler):
    """Same fan-out, but `close_session` always raises - simulating
    `Crawl4AICrawler.close_session`'s own watchdog
    (`session_cleanup_timeout_seconds`) firing during periodic recycling.
    `_recycle_session_if_due`'s existing broad `except` must recover from
    this and keep the crawl going, not let a hung/failed recycle attempt
    take the whole worker down with it."""

    async def close_session(self, session_id: str) -> None:
        raise RuntimeError(f"close_session watchdog: {session_id!r} did not close within 10s")


def test_recycle_session_failure_does_not_stop_the_crawl():
    fake = _FakeSessionRecycleFailsCrawler(n_pages=8)
    engine = CrawlEngineCore(fake, config=EngineCoreConfig(page_concurrency=1, session_recycle_after=3))
    results = asyncio.run(engine.run(fake.root_url))

    # Every page still gets visited despite every single recycle attempt
    # failing - a hung/failed close_session() must never hang or crash the
    # worker that happened to trigger it.
    assert len(results) == 9  # 1 root + 8 leaves


def test_session_never_recycled_when_disabled():
    fake = _FakeSessionRecyclingCrawler(n_pages=8)
    engine = CrawlEngineCore(fake, config=EngineCoreConfig(page_concurrency=1, session_recycle_after=None))
    asyncio.run(engine.run(fake.root_url))

    assert fake.closed_session_ids == []
