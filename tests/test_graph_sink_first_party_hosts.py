"""A decoupled backend (a site's own API on a different domain, e.g. a
Supabase project host) must persist like any same-domain call, while a
genuine third party on the same crawl keeps the asymmetric call_count-only
retention. Issue #209.

Runs against LadybugGraphStore in-memory mode with no browser:
`record_page_network` is called directly, which is the whole surface under
test.
"""
import asyncio

from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "app.example"
BASE_URL = "https://app.example/"
BACKEND_HOST = "backend.supabase.co"
TRACKER_HOST = "tracker.example"

REQUESTS = [
    {"method": "GET", "host": BACKEND_HOST, "path": "/functions/v1/things", "status": 200},
    {"method": "GET", "host": TRACKER_HOST, "path": "/collect", "status": 200},
]


def _record(sink: GraphStoreSink) -> None:
    asyncio.run(sink.record_page_network("app.example/", REQUESTS))


def test_allowlisted_host_persists_a_request_with_schema():
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL, first_party_hosts=[BACKEND_HOST]))

    endpoints = {r.endpoint for r in store.get_inferred_requests()}
    assert any(BACKEND_HOST in endpoint for endpoint in endpoints)


def test_non_allowlisted_host_still_only_bumps_call_count():
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL, first_party_hosts=[BACKEND_HOST]))

    endpoints = {r.endpoint for r in store.get_inferred_requests()}
    assert not any(TRACKER_HOST in endpoint for endpoint in endpoints)


def test_no_allowlist_keeps_the_decoupled_backend_third_party():
    """The pre-#209 behavior: an unlisted off-domain host, however much it's
    actually this application's own backend, still loses its schema."""
    store = LadybugGraphStore(SITE)
    _record(GraphStoreSink(store, base_url=BASE_URL))

    endpoints = {r.endpoint for r in store.get_inferred_requests()}
    assert not any(BACKEND_HOST in endpoint for endpoint in endpoints)
