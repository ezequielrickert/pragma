"""`CrawlEngineCore`'s scout mode - the mode `pragma static` runs under: a
single scout sweep, no interact phase, ever. Same fake-crawler approach as
test_crawl_resume.py - the seam under test is which pages get visited and
what status they land in, not what a real browser does.

Drives the crawl through `CrawlEngineCore` (issue #241), not the retired
`MechanicalCrawler` (issue #242) - scout mode's own behavior is unchanged,
only its harness moved. Overlaps `test_engine_core.py`'s own scout-mode
coverage; kept as its own file since it predates that one and still reads
cleanly on its own. Issue #249 moved discovery onto `Crawl4AICrawler
.deep_crawl` (`PragmaBestFirstStrategy.arun()`), so `_ScoutOnlyCrawler`
plays `arun_many`, the seam that strategy itself calls - see
test_engine_core.py's own fake for the same approach.
"""
import asyncio
from typing import Any, Dict, List, Optional

from crawl4ai import CrawlerRunConfig

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.engine_core import SCOUT, CrawlEngineCore, EngineCoreConfig
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "shop.example"
START = "http://shop.example/"


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaBestFirstStrategy.link_discovery` to work against."""

    def __init__(self, url: str, links: Optional[List[Dict[str, str]]] = None) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.error_message = ""
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": links or [], "external": []}
        self.metadata: Dict[str, Any] = {}
        self.session_id: Optional[str] = None


class _ScoutOnlyCrawler:
    """Answers discovery with one link to a second page; has no
    click/fill - an interact phase reaching this crawler at all raises
    AttributeError, which is exactly the failure a broken scout mode
    should produce."""

    async def arun_many(self, urls: List[str], config: CrawlerRunConfig, dispatcher: Any = None):
        async def gen():
            for url in urls:
                links = [] if "cart" in url else [{"href": "http://shop.example/cart"}]
                result = _FakeResult(url, links)
                result.session_id = f"session::{url}"
                yield result
        return gen()

    async def deep_crawl(self, start_url: str, strategy):
        config = CrawlerRunConfig(deep_crawl_strategy=strategy, stream=True)
        async for result in await strategy.arun(start_url, self, config):
            session_id = result.session_id or result.url
            state = PageState(url=result.url, components=[], links=[])
            yield state, result, session_id

    async def close_session(self, session_id: str) -> None:
        return None


def test_scout_only_visits_every_page_but_marks_them_scouted_not_finished():
    store = LadybugGraphStore(SITE)
    store.connect()
    sink = GraphStoreSink(store, base_url=START)
    engine = CrawlEngineCore(_ScoutOnlyCrawler(), config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(engine.run(START, mode=SCOUT))

    scouted = store.get_scouted()
    assert any("cart" in url for url in scouted)
    finished, _ = store.count_visited()
    assert finished == 0
