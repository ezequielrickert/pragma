"""Integration coverage for the exact-tier interact-once path -
`ExactReuseIndex` wired into `PageInteractionStep` (issue #140, ported
through issue #240's own rebuild): a canonical `Component` reused across
pages is clicked at most once, its outcome inferred onto every other page
as a `NAVIGATES_TO` edge instead of a second live click. Same fake-crawler
approach as test_engine_core.py.

Drives the crawl through `CrawlEngineCore` (issue #241), not the retired
`MechanicalCrawler` (issue #242) - `ExactReuseIndex` wiring itself is
unchanged, only its harness moved.
"""
import asyncio
from typing import Any, Dict, List, Tuple

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
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": [], "external": []}
        self.metadata: Dict[str, Any] = {}


class _TwoPagesSharedNavLinkCrawler:
    """Two pages, each carrying a component with the exact same content
    identity - clicking either one navigates to `SALE`. Which of the two
    pages' workers reaches the exact-reuse check first isn't something a
    test should assume (`page_concurrency` runs both as concurrent
    tasks); what's under test is that exactly one of them ever really
    clicks, not which."""

    def __init__(self) -> None:
        self.clicked: List[Tuple[str, str]] = []

    async def discover_page_with_result(self, url: str, session_id: str = ""):
        if url == HOME:
            state = PageState(url=HOME, components=[_nav_link("#nav-home")])
        elif url == CATALOG:
            state = PageState(url=CATALOG, components=[_nav_link("#nav-catalog")])
        else:
            state = PageState(url=url, components=[])
        return state, _FakeResult(url)

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
