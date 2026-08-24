"""GraphStoreSink no longer classifies a request's host as first- or
third-party at all - every observed request, on any host, persists as a
full Request node with schema. Issue #210 (reverses #209's per-site
allowlist, which turned out to be pure config overhead).

Runs against LadybugGraphStore in-memory mode with no browser:
`record_page_network` is called directly, which is the whole surface under
test.
"""
import asyncio

from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink

SITE = "app.example"
BASE_URL = "https://app.example/"
TRACKER_HOST = "tracker.example"

REQUESTS = [{"method": "GET", "host": TRACKER_HOST, "path": "/collect", "status": 200}]


def test_an_off_domain_host_still_persists_a_full_request():
    """The pre-#209 asymmetric behavior (an off-domain host loses its
    schema) no longer applies - #210 dropped the classifier outright."""
    store = LadybugGraphStore(SITE)
    asyncio.run(GraphStoreSink(store, base_url=BASE_URL).record_page_network("app.example/", REQUESTS))

    endpoints = {r.endpoint for r in store.get_inferred_requests()}
    assert any(TRACKER_HOST in endpoint for endpoint in endpoints)
