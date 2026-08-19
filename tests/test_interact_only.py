"""`MechanicalCrawlerConfig.interact_only` - the mode `pragma dynamic` runs
under when it's resuming a prior `pragma static` run. Same fake-crawler
approach as test_scout_only.py; `directory=tmp_path` keeps each test's
LadybugGraphStore isolated from every other test using the same site name.
"""
import asyncio

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig
from utils.urls import route_shape

SITE = "shop.example"
START = "http://shop.example/"
CART = "http://shop.example/cart"


class _NoDiscoveryCrawler:
    """Answers discovery for whatever URL it's asked - an interact_only run
    that wrongly tried to discover start_url from scratch would still reach
    this fake, so the real assertion under test is which pages ended up
    Finished, not whether discovery itself would fail."""

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        return PageState(url=url, components=[], links=[])

    async def close_session(self, session_id: str) -> None:
        return None


def _seed_scouted(store: LadybugGraphStore) -> None:
    """Seeds the two pages as scout() itself would leave them: keyed by
    `route_shape`, the same key `interact()` writes back to when it later
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
    mech = MechanicalCrawler(
        _NoDiscoveryCrawler(),
        config=MechanicalCrawlerConfig(sink=sink, base_url=START, interact_only=True),
    )

    asyncio.run(mech.crawl_site(START))

    finished, total = store.count_visited()
    assert finished == 2
    assert total == 2


def test_interact_only_never_enqueues_start_url_beyond_what_was_scouted(tmp_path):
    """A site with nothing scouted yet leaves interact_only with nothing to
    do - it must not fall back to discovering start_url itself, unlike the
    default fused pass."""
    store = LadybugGraphStore(SITE, directory=str(tmp_path))
    store.connect()

    sink = GraphStoreSink(store, base_url=START)
    mech = MechanicalCrawler(
        _NoDiscoveryCrawler(),
        config=MechanicalCrawlerConfig(sink=sink, base_url=START, interact_only=True),
    )

    asyncio.run(mech.crawl_site(START))

    finished, total = store.count_visited()
    assert finished == 0
    assert total == 0
