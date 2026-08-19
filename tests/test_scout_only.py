"""`MechanicalCrawlerConfig.scout_only` - the mode `pragma static` runs
under: a single scout sweep, no interact phase, ever. Same fake-crawler
approach as test_crawl_resume.py - the seam under test is which pages get
visited and what status they land in, not what a real browser does.
"""
import asyncio

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig

SITE = "shop.example"
START = "http://shop.example/"


class _ScoutOnlyCrawler:
    """Answers discovery with one link to a second page; has no
    click/fill - an interact phase reaching this crawler at all raises
    AttributeError, which is exactly the failure a broken `scout_only`
    should produce."""

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        links = [] if "cart" in url else [{"href": "http://shop.example/cart", "text": "Cart"}]
        return PageState(url=url, components=[], links=links)

    async def close_session(self, session_id: str) -> None:
        return None


def test_scout_only_visits_every_page_but_marks_them_scouted_not_finished():
    store = LadybugGraphStore(SITE)
    store.connect()
    sink = GraphStoreSink(store, base_url=START)
    mech = MechanicalCrawler(
        _ScoutOnlyCrawler(),
        config=MechanicalCrawlerConfig(sink=sink, base_url=START, scout_only=True),
    )

    asyncio.run(mech.crawl_site(START))

    scouted = store.get_scouted()
    assert any("cart" in url for url in scouted)
    finished, _ = store.count_visited()
    assert finished == 0
