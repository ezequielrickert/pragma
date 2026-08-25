"""A crawl that stopped early resumes from what the graph still calls Pending.

`GraphStore.get_pending` has been on the interface and in both backends since
the graph store existed, with no caller: the frontier only ever seeded
`start_url`, so a run that was cut short had to re-derive everything by
re-walking from the entry point, and could only reach a pending page that was
still linked from that path.

These use a fake crawler rather than a browser - the seam under test is which
URLs reach the frontier, not what happens once one is fetched. Drives the
crawl through `CrawlEngineCore` (issue #241), not the retired
`MechanicalCrawler` (issue #242) - `_resume_urls` was ported into it
unchanged (its own docstring says so), so this file's coverage carries over
one for one. Issue #249 moved discovery onto `PragmaBestFirstStrategy.arun()`
(seeded with a `resume_state` built from `_resume_urls`, see
`CrawlEngineCore._seed_resume_state`) - `_RecordingCrawler.arun_many` is the
seam that strategy itself calls, same real-frontier-logic approach as
test_engine_core.py's own fake.
"""
import asyncio
from typing import Any, Dict, List, Optional

from crawl4ai import CrawlerRunConfig

from core.interfaces import PageState
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.engine_core import CrawlEngineCore, EngineCoreConfig
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "shop.example"
START = "http://shop.example/"


class _FakeResult:
    """Just enough of crawl4ai's own `CrawlResult` for
    `PragmaBestFirstStrategy.link_discovery` to work against - no links,
    since every URL here arrives via `_resume_urls`, not link discovery."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.redirected_url = None
        self.success = True
        self.error_message = ""
        self.links: Dict[str, List[Dict[str, str]]] = {"internal": [], "external": []}
        self.metadata: Dict[str, Any] = {}
        self.session_id: Optional[str] = None


class _RecordingCrawler:
    """Answers every discovery with an empty page and remembers the order
    URLs were actually fetched in - `arun_many` is the seam
    `PragmaBestFirstStrategy._arun_best_first` itself calls."""

    def __init__(self) -> None:
        self.fetched: List[str] = []

    async def arun_many(self, urls: List[str], config: CrawlerRunConfig, dispatcher: Any = None):
        async def gen():
            for url in urls:
                self.fetched.append(url)
                result = _FakeResult(url)
                result.session_id = f"session::{url}"
                yield result
        return gen()

    async def deep_crawl(self, start_url: str, strategy):
        config = CrawlerRunConfig(deep_crawl_strategy=strategy, stream=True)
        async for result in await strategy.arun(start_url, self, config):
            session_id = result.session_id or result.url
            state = None if not result.success else PageState(url=result.url, components=[], links=[])
            yield state, result, session_id

    async def close_session(self, session_id: str) -> None:
        return None


def _crawl(store: LadybugGraphStore) -> _RecordingCrawler:
    crawler = _RecordingCrawler()
    sink = GraphStoreSink(store, base_url=START)
    engine = CrawlEngineCore(crawler, config=EngineCoreConfig(sink=sink, base_url=START))
    asyncio.run(engine.run(START))
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
    """Without a graph store there is no previous run to read, and
    `CrawlEngineCore.run` must still work - it just starts from the entry
    point alone."""
    crawler = _RecordingCrawler()
    engine = CrawlEngineCore(crawler, config=EngineCoreConfig(base_url=START))
    asyncio.run(engine.run(START))

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
