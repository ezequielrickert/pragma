"""A crawl that stopped early resumes from what the graph still calls Pending.

`GraphStore.get_pending` has been on the interface and in both backends since
the graph store existed, with no caller: the frontier only ever seeded
`start_url`, so a run that was cut short had to re-derive everything by
re-walking from the entry point, and could only reach a pending page that was
still linked from that path.

These use a fake crawler rather than a browser - the seam under test is which
URLs reach the frontier, not what happens once one is fetched.
"""
import asyncio
from typing import List

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from spiders.orchestration.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig

SITE = "shop.example"
START = "http://shop.example/"


class _RecordingCrawler:
    """Answers every discovery with an empty page and remembers the order."""

    def __init__(self) -> None:
        self.fetched: List[str] = []

    async def discover_page(self, url: str, session_id: str = "") -> PageState:
        self.fetched.append(url)
        return PageState(url=url, components=[], links=[])

    async def close_session(self, session_id: str) -> None:
        return None


def _crawl(store: LadybugGraphStore) -> _RecordingCrawler:
    crawler = _RecordingCrawler()
    sink = GraphStoreSink(store, base_url=START)
    mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(sink=sink, base_url=START))
    asyncio.run(mech.crawl_site(START))
    return crawler


def test_a_pending_page_from_a_previous_run_is_picked_up():
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/cart", status="Pending")

    crawler = _crawl(store)

    assert any("cart" in url for url in crawler.fetched)


def test_a_finished_page_is_not_revisited():
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/done", status="Finished")

    crawler = _crawl(store)

    assert not any("done" in url for url in crawler.fetched)


def test_an_external_page_is_never_resumed():
    """status=External marks an off-domain target the frontier refuses; it
    must not come back as resumable work."""
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("instagram.com/shop", status="External")

    crawler = _crawl(store)

    assert not any("instagram" in url for url in crawler.fetched)


def test_a_shaped_token_url_is_not_fetched():
    """route_shape collapses opaque segments to a literal `{token}`, which is
    a storage key and not an address - there is nothing to navigate to."""
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/o/{token}", status="Pending")

    crawler = _crawl(store)

    assert not any("{token}" in url for url in crawler.fetched)


def test_the_entry_point_is_still_visited_first():
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/cart", status="Pending")

    crawler = _crawl(store)

    assert crawler.fetched[0] == START


def test_no_sink_means_nothing_to_resume_from():
    """Without a graph store there is no previous run to read, and crawl_site
    must still work - it just starts from the entry point alone."""
    crawler = _RecordingCrawler()
    mech = MechanicalCrawler(crawler, config=MechanicalCrawlerConfig(base_url=START))
    asyncio.run(mech.crawl_site(START))

    assert crawler.fetched == [START]


def test_a_sampled_route_shape_is_not_sampled_again_next_run():
    """max_visits_per_route_shape was per-run, not per-site: the counter
    lived only in memory, so each resume started it at zero and a site
    crawled in five short runs sampled up to five URLs of a shape where one
    long run sampled one. Same site, two different graphs."""
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/o/{token}", status="Finished")
    store.upsert_page("shop.example/o/aB1cD2eF3gH4iJ5kL6mN", status="Pending")

    crawler = _crawl(store)

    assert not any("/o/" in url for url in crawler.fetched)


def test_an_unfinished_shape_is_still_open():
    """Priming must not lock out a shape nothing has completed yet."""
    store = LadybugGraphStore(SITE)
    store.connect()
    store.upsert_page("shop.example/cart", status="Pending")

    crawler = _crawl(store)

    assert any("cart" in url for url in crawler.fetched)
