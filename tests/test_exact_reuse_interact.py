"""Integration coverage for the exact-tier interact-once path -
`ExactReuseIndex` wired into `PageInteractionStep` (issue #140, ported
through issue #240's own rebuild): a canonical `Component` reused across
pages is clicked at most once, its outcome inferred onto every other page
as a `NAVIGATES_TO` edge instead of a second live click. Same fake-crawler
approach as test_engine_core.py.

Drives the crawl through `CrawlEngineCore` (issue #241), not the retired
`MechanicalCrawler` (issue #242) - `ExactReuseIndex` wiring itself is
unchanged, only its harness moved. Issue #249 moved interact mode's flat
pass onto `Crawl4AICrawler.discover_many` (`arun_many`+
`SessionAwareDispatcher`) - both pages are fetched concurrently through
that one call, same "which worker gets there first is unspecified" property
this test always relied on, just driven by the dispatcher now instead of a
hand-rolled worker pool.
"""
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from crawl4ai import CrawlerRunConfig

from analysis.exact_reuse_index import ExactReuseIndex
from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from generators.ledger import flat_component_ledger
from spiders.orchestration.engine_core import INTERACT, CrawlEngineCore, EngineCoreConfig
from spiders.orchestration.graph_sink import GraphStoreSink
from utils.urls import route_shape

SITE = "shop.example"
HOME = "http://shop.example/"
CATALOG = "http://shop.example/catalog"
SALE = "http://shop.example/sale"


def _nav_link(path: str) -> dict:
    return {
        "tag": "a", "role": "", "name": "", "form": "", "text": "Big Sale",
        "path": path, "visible": True, "attributes": {},
    }


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaDeepCrawlStrategy.link_discovery` to work against."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.error_message = ""
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": [], "external": []}
        self.metadata: Dict[str, Any] = {}
        self.session_id: Optional[str] = None


class _TwoPagesSharedNavLinkCrawler:
    """Two pages, each carrying a component with the exact same content
    identity - clicking either one navigates to `SALE`. Which of the two
    pages' fetches the dispatcher resolves first isn't something a test
    should assume; what's under test is that exactly one of them ever
    really clicks, not which."""

    def __init__(self) -> None:
        self.clicked: List[Tuple[str, str]] = []

    def _state_for(self, url: str) -> PageState:
        if url == HOME:
            return PageState(url=HOME, components=[_nav_link("#nav-home")])
        if url == CATALOG:
            return PageState(url=CATALOG, components=[_nav_link("#nav-catalog")])
        return PageState(url=url, components=[])

    async def arun_many(self, urls: List[str], config: CrawlerRunConfig, dispatcher: Any = None):
        async def gen():
            for url in urls:
                result = _FakeResult(url)
                result.session_id = f"session::{url}"
                yield result
        return gen()

    async def discover_many(self, urls: List[str], dispatcher: Any = None):
        stream = await self.arun_many(urls, CrawlerRunConfig(stream=True), dispatcher)
        async for result in stream:
            session_id = result.session_id or result.url
            yield result.url, self._state_for(result.url), result, session_id

    async def discover_page_with_result(self, url: str, session_id: str = ""):
        """`_interact_with_resumes`'s own resume-after-navigation re-fetch
        still calls this directly, unchanged by issue #249."""
        return self._state_for(url), _FakeResult(url)

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.clicked.append((url, selector))
        return PageState(url=SALE, components=[])

    async def close_session(self, session_id: str) -> None:
        return None


def _seed_scouted_pages_with_reused_component(store: LadybugGraphStore) -> None:
    sink = GraphStoreSink(store, base_url=HOME)
    for url, path in ((HOME, "#nav-home"), (CATALOG, "#nav-catalog")):
        page_key = route_shape(url)
        asyncio.run(sink.record_page_arrival(page_key, description="", title=""))
        asyncio.run(sink.record_page_scouted(page_key, 1))
        # Byte-identical content -> one canonical Component row (issue
        # #136's write-time MERGE), reused across both pages.
        store.record_component(page_key, path, tag="a", text="Big Sale")


def test_exact_reuse_skips_the_second_page_and_infers_its_navigation_edge(tmp_path):
    store = LadybugGraphStore(SITE, directory=str(tmp_path))
    store.connect()
    _seed_scouted_pages_with_reused_component(store)

    exact_reuse_index = ExactReuseIndex(flat_component_ledger(store))
    sink = GraphStoreSink(store, base_url=HOME)
    fake = _TwoPagesSharedNavLinkCrawler()
    engine = CrawlEngineCore(
        fake, config=EngineCoreConfig(sink=sink, base_url=HOME, exact_reuse_index=exact_reuse_index),
    )

    asyncio.run(engine.run(HOME, mode=INTERACT))

    # Exactly one of the two pages' components was ever really clicked -
    # whichever page's worker reached the exact-reuse check first.
    assert len(fake.clicked) == 1

    home_key, catalog_key, sale_key = route_shape(HOME), route_shape(CATALOG), route_shape(SALE)
    destinations = {(e["from"], e["to"]) for e in store.get_edges()}
    # Both pages' NAVIGATES_TO -> SALE edges exist regardless of which
    # one fired the real click - the other's is inferred, not observed.
    assert (home_key, sale_key) in destinations
    assert (catalog_key, sale_key) in destinations
