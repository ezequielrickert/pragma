"""`CrawlEngineCore`'s interact mode - the mode `pragma dynamic` runs under
when it's resuming a prior `pragma static` run. Same fake-crawler approach
as test_scout_only.py; `directory=tmp_path` keeps each test's
LadybugGraphStore isolated from every other test using the same site name.

Drives the crawl through `CrawlEngineCore` (issue #241), not the retired
`MechanicalCrawler` (issue #242) - interact mode's own behavior is
unchanged, only its harness moved. `test_engine_core.py` covers the same
mode's happy path; this file's own
`test_interact_only_never_enqueues_start_url_beyond_what_was_scouted` is
the one assertion not duplicated there.
"""
import asyncio
from typing import Any, Dict, List

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.engine_core import INTERACT, CrawlEngineCore, EngineCoreConfig
from spiders.orchestration.graph_sink import GraphStoreSink
from utils.urls import route_shape

SITE = "shop.example"
START = "http://shop.example/"
CART = "http://shop.example/cart"


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaDeepCrawlStrategy.link_discovery` to work against."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": [], "external": []}
        self.metadata: Dict[str, Any] = {}


class _NoDiscoveryCrawler:
    """Answers discovery for whatever URL it's asked - an interact-mode run
    that wrongly tried to discover start_url from scratch would still reach
    this fake, so the real assertion under test is which pages ended up
    Finished, not whether discovery itself would fail. Also refuses a
    schemeless URL, the same way crawl4ai's own `arun()` does ("URL must
    start with 'http://', 'https://', 'file://', or 'raw:'") - `get_scouted()`
    hands back a bare `route_shape` key, not a navigable URL, so a caller
    that forgot to restore its scheme would be caught here rather than
    silently passing against a fake that doesn't care.
    """

    async def discover_page_with_result(self, url: str, session_id: str = ""):
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with 'http://' or 'https://', got {url!r}")
        return PageState(url=url, components=[], links=[]), _FakeResult(url)

    async def close_session(self, session_id: str) -> None:
        return None


def _seed_scouted(store: LadybugGraphStore) -> None:
    """Seeds the two pages as scout mode itself would leave them: keyed by
    `route_shape`, the same key interact mode later writes back to when it
    marks them Finished - a raw (unshaped) key here would land on a
    different page node and the two counts would never converge."""
    sink = GraphStoreSink(store, base_url=START)
    for url in (START, CART):
        page_key = route_shape(url)
        asyncio.run(sink.record_page_arrival(page_key, description="", title=""))
        asyncio.run(sink.record_page_scouted(page_key, 0))


def test_interact_only_visits_exactly_the_scouted_pages_and_marks_them_finished(tmp_path):
    store = LadybugGraphStore(SITE, directory=str(tmp_path))
    store.connect()
    _seed_scouted(store)

    sink = GraphStoreSink(store, base_url=START)
    engine = CrawlEngineCore(_NoDiscoveryCrawler(), config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(engine.run(START, mode=INTERACT))

    finished, total = store.count_visited()
    assert finished == 2
    assert total == 2


def test_interact_only_never_enqueues_start_url_beyond_what_was_scouted(tmp_path):
    """A site with nothing scouted yet leaves interact mode with nothing to
    do - it must not fall back to discovering start_url itself, unlike the
    default fused pass."""
    store = LadybugGraphStore(SITE, directory=str(tmp_path))
    store.connect()

    sink = GraphStoreSink(store, base_url=START)
    engine = CrawlEngineCore(_NoDiscoveryCrawler(), config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(engine.run(START, mode=INTERACT))

    finished, total = store.count_visited()
    assert finished == 0
    assert total == 0
