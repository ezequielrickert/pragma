"""Tests for core/caching_graph_store.py - built against a small counting
fake, not a real graph store backend: the whole point is verifying *how
many times* the inner store gets called, which a real backend's own
correctness tests don't check."""
from core.caching_graph_store import CachingGraphStore


class _CountingStore:
    """Records how many times each method actually ran - what a real
    store backend would do underneath, minus the cost of caring which
    one. No `site` argument anywhere: the store this wraps is already
    scoped to exactly one site by construction, unlike the retired
    DuckDB backend this replaces."""

    def __init__(self) -> None:
        self.call_counts = {}

    def get_component_ledger(self):
        self.call_counts["get_component_ledger"] = self.call_counts.get("get_component_ledger", 0) + 1
        return {"page": {"path": {"text": "ledger"}}}

    def get_edges(self):
        self.call_counts["get_edges"] = self.call_counts.get("get_edges", 0) + 1
        return [{"from": "a", "to": "b"}]

    def get_component_states(self, page_url):
        """A parameterized read - deliberately not in _CACHED_READS."""
        self.call_counts["get_component_states"] = self.call_counts.get("get_component_states", 0) + 1
        return {"path": {"text": f"state for {page_url}"}}

    def record_edge(self, from_url, to_url, component, action, run_id=""):
        self.call_counts["record_edge"] = self.call_counts.get("record_edge", 0) + 1

    def close(self):
        self.call_counts["close"] = self.call_counts.get("close", 0) + 1


def test_a_cached_read_hits_the_inner_store_only_once():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    first = store.get_component_ledger()
    second = store.get_component_ledger()
    third = store.get_component_ledger()

    assert first == second == third
    assert inner.call_counts["get_component_ledger"] == 1


def test_different_cached_methods_are_cached_independently():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.get_component_ledger()
    store.get_edges()
    store.get_edges()

    assert inner.call_counts["get_component_ledger"] == 1
    assert inner.call_counts["get_edges"] == 1


def test_a_parameterized_read_is_never_cached():
    """get_component_states(page_url) isn't in _CACHED_READS - every call
    must reach the inner store, since a cache keyed on nothing would
    return the wrong page's state."""
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.get_component_states("/a")
    store.get_component_states("/b")
    store.get_component_states("/a")

    assert inner.call_counts["get_component_states"] == 3


def test_writes_pass_through_uncached_every_time():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.record_edge("a", "b", "link", "click")
    store.record_edge("a", "b", "link", "click")

    assert inner.call_counts["record_edge"] == 2


def test_close_delegates_to_the_inner_store():
    inner = _CountingStore()
    store = CachingGraphStore(inner)

    store.close()

    assert inner.call_counts["close"] == 1
