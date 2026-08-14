"""Unit tests for GraphStoreInteractionTracker's local read cache
(docs/explicativos/plan-almacenamiento.md Fase A/B - "the N+1 read pattern"
finding). Uses a spy GraphStore (same pattern as
tests/test_graph_store.py::_SpyGraphStore) to assert the actual round-trip
count directly, not just the resulting boolean - the whole point of this
change is fewer GraphStore calls, which a plain correctness test on the
boolean result alone wouldn't catch a regression on.
"""
from spiders.orchestration.graph_sink import GraphStoreInteractionTracker
from database.memory_graph_store import InMemoryGraphStore

SITE = "cache-test-site"


class _SpyGraphStore(InMemoryGraphStore):
    """Counts real get_component_states/is_visited calls."""

    def __init__(self) -> None:
        super().__init__()
        self.get_component_states_calls = 0
        self.is_visited_calls = 0

    def get_component_states(self, site, page_url):
        self.get_component_states_calls += 1
        return super().get_component_states(site, page_url)

    def is_visited(self, site, url):
        self.is_visited_calls += 1
        return super().is_visited(site, url)


def _store_with_page(page_url: str, *paths_interacted: str) -> _SpyGraphStore:
    store = _SpyGraphStore()
    store.connect()
    store.upsert_page(SITE, page_url, status="Pending")
    store.record_component(SITE, page_url, "a", tag="button")
    store.record_component(SITE, page_url, "b", tag="button")
    store.record_component(SITE, page_url, "c", tag="button")
    for path in paths_interacted:
        store.record_component_interaction(SITE, page_url, path, action="click")
    return store


def test_is_interacted_hits_the_store_at_most_once_per_page():
    store = _store_with_page("example.com", "a")
    tracker = GraphStoreInteractionTracker(store, SITE)

    # Same shape as MechanicalCrawler._visit_page's frontier loop: many
    # is_interacted checks against the same page in one pass.
    results = [tracker.is_interacted("example.com", p) for p in ("a", "b", "c", "a", "b", "c")]

    assert results == [True, False, False, True, False, False]
    assert store.get_component_states_calls == 1, "must read the page's state once, not once per check"


def test_is_interacted_caches_per_page_independently():
    store = _store_with_page("example.com/a", "x")
    store.upsert_page(SITE, "example.com/b", status="Pending")
    store.record_component(SITE, "example.com/b", "x", tag="button")
    tracker = GraphStoreInteractionTracker(store, SITE)

    assert tracker.is_interacted("example.com/a", "x") is True
    assert tracker.is_interacted("example.com/b", "x") is False
    assert tracker.is_interacted("example.com/a", "x") is True
    assert store.get_component_states_calls == 2, "one read per distinct page, not shared/collapsed across pages"


def test_mark_interacted_updates_the_cache_without_a_second_store_write():
    store = _store_with_page("example.com")
    tracker = GraphStoreInteractionTracker(store, SITE)

    assert tracker.is_interacted("example.com", "a") is False  # populates the cache
    tracker.mark_interacted("example.com", "a")
    assert tracker.is_interacted("example.com", "a") is True  # served from cache, no extra read

    assert store.get_component_states_calls == 1, "mark_interacted must not trigger a real GraphStore read"
    # And it must never write to the real store either - GraphStoreSink owns
    # that (see GraphStoreSink.record_interaction) - the real store's own
    # state is untouched by mark_interacted alone.
    real_states = store.get_component_states(SITE, "example.com")
    assert real_states["a"]["interacted"] is False


def test_mark_interacted_works_for_a_path_never_read_into_the_cache_yet():
    """A component can be marked interacted (e.g. a failed-interaction path)
    without ever having gone through record_component/an is_interacted check
    first - mark_interacted must not assume the page is already cached."""
    store = _store_with_page("example.com")
    tracker = GraphStoreInteractionTracker(store, SITE)

    tracker.mark_interacted("example.com", "never-seen-before")
    assert tracker.is_interacted("example.com", "never-seen-before") is True
    # mark_interacted itself never touches the store (dict.setdefault only);
    # the subsequent is_interacted call is served entirely from that same
    # cache entry, so this never triggers a real GraphStore read at all.
    assert store.get_component_states_calls == 0, "mark_interacted + is_interacted on the same path must never hit the store"


def test_is_visited_hits_the_store_at_most_once_per_page():
    store = _SpyGraphStore()
    store.connect()
    store.upsert_page(SITE, "example.com", status="Finished")
    tracker = GraphStoreInteractionTracker(store, SITE)

    results = [tracker.is_visited("example.com") for _ in range(5)]

    assert all(results)
    assert store.is_visited_calls == 1, "must read once, not once per _enqueue/_worker check"


def test_mark_visited_updates_cache_without_a_second_store_write():
    store = _SpyGraphStore()
    store.connect()
    store.upsert_page(SITE, "example.com", status="Pending")
    tracker = GraphStoreInteractionTracker(store, SITE)

    assert tracker.is_visited("example.com") is False
    tracker.mark_visited("example.com")
    assert tracker.is_visited("example.com") is True

    assert store.is_visited_calls == 1
    # The real store's own status must be untouched by mark_visited alone -
    # GraphStoreSink.record_page_finished owns the real write.
    assert store.get_progress_table_rows(SITE)[0]["status"] == "Pending"


def test_fresh_tracker_instance_reads_real_store_state_not_a_stale_cache():
    """Regression guard for the cross-instance case
    (tests/test_graph_sink.py::test_graph_backed_tracker_prevents_re_interaction_across_a_fresh_mechanical_crawler):
    a brand new tracker instance against a store another tracker already
    wrote to must see that real state on its very first check."""
    store = _store_with_page("example.com", "a")
    tracker1 = GraphStoreInteractionTracker(store, SITE)
    assert tracker1.is_interacted("example.com", "a") is True

    tracker2 = GraphStoreInteractionTracker(store, SITE)  # fresh cache
    assert tracker2.is_interacted("example.com", "a") is True
    assert store.get_component_states_calls == 2, "each tracker instance reads independently, once"
