"""GraphStoreSink must judge a link's scope the same way UrlFrontier does.

Before this, `is_in_scope` was called in exactly one place - the frontier -
so the sink recorded a Pending Page for every http(s) link target including
off-domain ones the frontier would always refuse. Those pages then sat in
`get_pending()` forever as work that could never be done, and counted toward
`count_visited`'s total so coverage could never reach 100% on any site that
links outward.

Runs against LadybugGraphStore in-memory mode with no browser:
`record_inventory` is called directly, which is the whole surface under
test.
"""
import asyncio

from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "shop.example"
BASE_URL = "https://shop.example/"

LINKS = [
    {"href": "https://shop.example/cart", "text": "Cart", "scheme": "https"},
    {"href": "https://shop.example/help", "text": "Help", "scheme": "https"},
    {"href": "https://instagram.com/shop", "text": "Instagram", "scheme": "https"},
    {"href": "mailto:hi@shop.example", "text": "Mail", "scheme": "mailto"},
]


def _link_label(store: LadybugGraphStore, from_url: str, to_url: str):
    rows = store._call(lambda conn: list(conn.execute(
        "MATCH (:Page {url: $from})-[l:LINKS_TO]->(:Page {url: $to}) RETURN l.label",
        {"from": from_url, "to": to_url},
    )))
    return rows[0][0] if rows else None


def _record(sink: GraphStoreSink) -> None:
    asyncio.run(sink.record_inventory("shop.example/", [], LINKS))


def test_off_domain_link_targets_are_not_pending_work():
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL))

    pending = store.get_pending()
    assert "shop.example/cart" in pending
    assert "shop.example/help" in pending
    assert not any("instagram" in url for url in pending)


def test_off_domain_targets_stay_recorded_as_links():
    """Marked, not dropped - where a site sends you is real data, and the
    LINKS_TO edge is what carries it."""
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL))

    assert _link_label(store, "shop.example/", "instagram.com/shop") == "Instagram"


def test_coverage_total_excludes_pages_the_crawl_can_never_visit():
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL))

    _, total = store.count_visited()
    # The page itself plus its two in-scope targets. Instagram is excluded, so
    # finishing this site is arithmetically possible.
    assert total == 3


def test_no_base_url_keeps_the_pre_scope_behavior():
    """`base_url=None` disables the check outright, so a caller that never
    passes one (tests, mostly) sees exactly what it saw before."""
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store))

    assert any("instagram" in url for url in store.get_pending())


def test_subdomains_follow_the_allow_subdomains_flag():
    links = [{"href": "https://blog.shop.example/post", "text": "Blog", "scheme": "https"}]

    strict = LadybugGraphStore(SITE)
    asyncio.run(GraphStoreSink(strict, base_url=BASE_URL).record_inventory("shop.example/", [], links))
    assert not any("blog." in url for url in strict.get_pending())

    permissive = LadybugGraphStore(SITE)
    asyncio.run(
        GraphStoreSink(permissive, base_url=BASE_URL, allow_subdomains=True)
        .record_inventory("shop.example/", [], links)
    )
    assert any("blog." in url for url in permissive.get_pending())
