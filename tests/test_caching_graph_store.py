"""Tests for core/caching_graph_store.py - built against a small counting
fake, not a real GraphStore backend: the whole point is verifying *how
many times* the inner store gets called, which a real backend's own
correctness tests don't check."""
from core.caching_graph_store import CachingGraphStore


class _CountingStore:
    """Records how many times each method actually ran, per site - what a
    real GraphStore backend would do underneath, minus the cost of caring
    which one."""

    def __init__(self) -> None:
        self.call_counts = {}

    def get_component_ledger(self, site):
        self.call_counts["get_component_ledger"] = self.call_counts.get("get_component_ledger", 0) + 1
        return {"page": {"path": {"text": f"ledger for {site}"}}}

    def get_edges(self, site):
        self.call_counts["get_edges"] = self.call_counts.get("get_edges", 0) + 1
        return [{"from": "a", "to": "b"}]

    def get_page_label(self, site, url):
        """A parameterized read - deliberately not in _CACHED_READS."""
        self.call_counts["get_page_label"] = self.call_counts.get("get_page_label", 0) + 1
        return f"label for {url}"

    def record_edge(self, site, from_url, to_url, component, action, run_id=""):
        self.call_counts["record_edge"] = self.call_counts.get("record_edge", 0) + 1

    def close(self):
        self.call_counts["close"] = self.call_counts.get("close", 0) + 1


def test_a_cached_read_hits_the_inner_store_only_once():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    first = store.get_component_ledger("site.com")
    second = store.get_component_ledger("site.com")
    third = store.get_component_ledger("site.com")

    assert first == second == third
    assert inner.call_counts["get_component_ledger"] == 1


def test_different_cached_methods_are_cached_independently():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.get_component_ledger("site.com")
    store.get_edges("site.com")
    store.get_edges("site.com")

    assert inner.call_counts["get_component_ledger"] == 1
    assert inner.call_counts["get_edges"] == 1


def test_different_sites_get_independent_cache_entries():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    a = store.get_component_ledger("a.com")
    b = store.get_component_ledger("b.com")
    store.get_component_ledger("a.com")

    assert a != b
    assert inner.call_counts["get_component_ledger"] == 2


def test_a_parameterized_read_is_never_cached():
    """get_page_label(site, url) isn't in _CACHED_READS - every call must
    reach the inner store, since a cache keyed on site alone would return
    the wrong url's label."""
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.get_page_label("site.com", "/a")
    store.get_page_label("site.com", "/b")
    store.get_page_label("site.com", "/a")

    assert inner.call_counts["get_page_label"] == 3


def test_writes_pass_through_uncached_every_time():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.record_edge("site.com", "a", "b", "link", "click")
    store.record_edge("site.com", "a", "b", "link", "click")

    assert inner.call_counts["record_edge"] == 2


def test_close_delegates_to_the_inner_store():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.close()

    assert inner.call_counts["close"] == 1
