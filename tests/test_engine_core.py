"""`CrawlEngineCore` - the shared engine core issue #241 assembles from
`PragmaDeepCrawlStrategy` (issue #239) and `PageInteractionStep` (issue
#240). Same fake-crawler approach as test_scout_only.py/test_crawl_resume.py
- the seam under test is which pages get discovered/interacted and what
status they land in, not what a real browser does (test_static_engine.py/
test_dynamic_engine.py already cover the real-browser path end to end).
"""
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from core.data_contracts import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.engine_core import FUSED, INTERACT, SCOUT, CrawlEngineCore, EngineCoreConfig
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "shop.example"
START = "http://shop.example/"
CART = "http://shop.example/cart"


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaDeepCrawlStrategy.link_discovery` to work against - `.links` is
    its own, crawl4ai-native extraction (a different shape from this
    project's `PageState.links`), not this test's `PageState.links`.
    """

    def __init__(self, url: str, links: Optional[List[Dict[str, str]]] = None) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.links = {"internal": links or [], "external": []}
        self.metadata: Dict[str, Any] = {}


class _FakeCrawler:
    """A fixed site graph: `pages` maps a URL to `(PageState, FakeResult)`.
    `click`/`fill` never navigate - every component this test wires is a
    same-URL no-op, which is all `CrawlEngineCore` needs to see a full
    discover-then-interact pass complete.
    """

    def __init__(self, pages: Dict[str, Tuple[PageState, _FakeResult]]) -> None:
        self.pages = pages
        self.clicked: List[Tuple[str, str]] = []

    async def discover_page_with_result(self, url: str, session_id: Optional[str] = None):
        return self.pages[url]

    async def close_session(self, session_id: str) -> None:
        return None

    async def click(self, url: str, session_id: str, path: str) -> PageState:
        self.clicked.append((url, path))
        state, _ = self.pages[url]
        return state


class _NavigatingFakeCrawler(_FakeCrawler):
    """Like `_FakeCrawler`, but `click` on `navigating_path` lands on
    `destination` instead of returning the origin page's own state -
    reproduces a listing card whose title link navigates while its
    later-in-DOM-order siblings (a modal trigger, a share/favorite button)
    stay same-URL.
    """

    def __init__(
        self,
        pages: Dict[str, Tuple[PageState, _FakeResult]],
        navigating_path: str,
        destination: PageState,
    ) -> None:
        super().__init__(pages)
        self.navigating_path = navigating_path
        self.destination = destination

    async def click(self, url: str, session_id: str, path: str) -> PageState:
        self.clicked.append((url, path))
        if path == self.navigating_path:
            return self.destination
        state, _ = self.pages[url]
        return state


def _store_and_sink():
    store = LadybugGraphStore(SITE)
    store.connect()
    return store, GraphStoreSink(store, base_url=START)


def test_scout_mode_discovers_the_whole_site_and_marks_every_page_scouted():
    pages = {
        START: (PageState(url=START, components=[], links=[]), _FakeResult(START, [{"href": CART}])),
        CART: (PageState(url=CART, components=[], links=[]), _FakeResult(CART)),
    }
    store, sink = _store_and_sink()
    core = CrawlEngineCore(_FakeCrawler(pages), config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(core.run(START, mode=SCOUT))

    scouted = store.get_scouted()
    assert any("cart" in url for url in scouted)
    finished, _ = store.count_visited()
    assert finished == 0


def test_fused_mode_discovers_and_interacts_and_marks_pages_finished():
    button = {"path": "#add", "tag": "button", "visible": True}
    pages = {
        START: (PageState(url=START, components=[button], links=[]), _FakeResult(START)),
    }
    store, sink = _store_and_sink()
    crawler = _FakeCrawler(pages)
    core = CrawlEngineCore(crawler, config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(core.run(START, mode=FUSED))

    assert crawler.clicked == [(START, "#add")]
    finished, total = store.count_visited()
    assert finished == 1
    assert total == 1
    assert store.get_scouted() == []


def test_interact_mode_skips_discovery_and_interacts_only_with_already_scouted_pages():
    store, sink = _store_and_sink()
    from utils.urls import route_shape

    page_key = route_shape(START)
    asyncio.run(sink.record_page_arrival(page_key, description="", title=""))
    asyncio.run(sink.record_page_scouted(page_key, 1))

    # `get_scouted()` returns storage keys restored to navigable URLs
    # (`restore_scheme`) without the trailing slash `route_shape` strips -
    # this test's fake crawler must be keyed the same way `_scouted_urls`
    # will actually look it up.
    scouted_url = "http://shop.example"
    button = {"path": "#add", "tag": "button", "visible": True}
    pages = {scouted_url: (PageState(url=scouted_url, components=[button], links=[]), _FakeResult(scouted_url))}
    crawler = _FakeCrawler(pages)
    core = CrawlEngineCore(crawler, config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(core.run(START, mode=INTERACT))

    assert crawler.clicked == [(scouted_url, "#add")]
    finished, _ = store.count_visited()
    assert finished == 1


def test_max_pages_stops_discovery_once_the_cap_is_reached():
    pages = {
        START: (PageState(url=START, components=[], links=[]), _FakeResult(START, [{"href": CART}])),
        CART: (PageState(url=CART, components=[], links=[]), _FakeResult(CART)),
    }
    store, sink = _store_and_sink()
    core = CrawlEngineCore(
        _FakeCrawler(pages), config=EngineCoreConfig(sink=sink, base_url=START, max_pages=1)
    )

    asyncio.run(core.run(START, mode=SCOUT))

    scouted = store.get_scouted()
    assert len(scouted) == 1


def test_a_navigating_click_earlier_in_dom_order_does_not_strand_later_same_url_components():
    """Issue #243: a listing card's title link navigates away partway
    through the frontier - the components after it (a modal trigger, a
    share/favorite button) must still get interacted with via a follow-up
    pass over the re-fetched origin page, not silently dropped."""
    nav_link = {"path": "#title-link", "tag": "a", "visible": True, "attributes": {"href": "/detail"}}
    modal_trigger = {"path": "#open-modal", "tag": "button", "visible": True}
    favorite_button = {"path": "#favorite", "tag": "button", "visible": True}
    origin_state = PageState(
        url=START, components=[nav_link, modal_trigger, favorite_button], links=[]
    )
    destination = PageState(url="http://shop.example/detail", components=[], links=[])
    pages = {START: (origin_state, _FakeResult(START))}
    store, sink = _store_and_sink()
    crawler = _NavigatingFakeCrawler(pages, navigating_path="#title-link", destination=destination)
    core = CrawlEngineCore(crawler, config=EngineCoreConfig(sink=sink, base_url=START))

    asyncio.run(core.run(START, mode=FUSED))

    assert sorted(crawler.clicked) == [
        (START, "#favorite"),
        (START, "#open-modal"),
        (START, "#title-link"),
    ]
    # `total` is 2, not 1: recording the navigation edge to `/detail` upserts
    # a placeholder Page node for it too, same as any navigating click whose
    # destination falls outside this run's frontier - unrelated to this
    # test's own concern, which is that the origin page itself finishes.
    finished, total = store.count_visited()
    assert finished == 1
    assert total == 2


def test_max_visits_per_route_shape_is_threaded_into_the_frontier():
    core = CrawlEngineCore(
        _FakeCrawler({}), config=EngineCoreConfig(base_url=START, max_visits_per_route_shape=3)
    )

    assert core.strategy.max_visits_per_route_shape == 3
