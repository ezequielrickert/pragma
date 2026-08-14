"""InteractionTracker backed by GraphStore reads.
Details: docs/dev/spiders/orchestration/graph_sink/tracker.md#module
"""
from __future__ import annotations

from typing import Any, Dict

from core.interfaces import GraphStore


class GraphStoreInteractionTracker:
    """`InteractionTracker` backed by `GraphStore` reads, with a per-instance
    local read cache. Details: docs/dev/spiders/orchestration/graph_sink/tracker.md#graphstoreinteractiontracker
    """

    def __init__(self, graph_store: GraphStore, site: str) -> None:
        self.graph_store = graph_store
        self.site = site
        # page_url -> {path: {..., "interacted": bool}}, populated lazily.
        self._states_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._visited_cache: Dict[str, bool] = {}  # page_url -> bool, same discipline.

    def _states_for(self, page_url: str) -> Dict[str, Dict[str, Any]]:
        if page_url not in self._states_cache:
            self._states_cache[page_url] = self.graph_store.get_component_states(self.site, page_url)
        return self._states_cache[page_url]

    def is_interacted(self, page_url: str, path: str) -> bool:
        return bool(self._states_for(page_url).get(path, {}).get("interacted"))

    def mark_interacted(self, page_url: str, path: str) -> None:
        """Cache-only; `GraphStoreSink.record_interaction` does the real write.
        Details: docs/dev/spiders/orchestration/graph_sink/tracker.md#mark_interacted
        """
        self._states_cache.setdefault(page_url, {}).setdefault(path, {})["interacted"] = True

    def is_visited(self, page_url: str) -> bool:
        if page_url not in self._visited_cache:
            self._visited_cache[page_url] = self.graph_store.is_visited(self.site, page_url)
        return self._visited_cache[page_url]

    def mark_visited(self, page_url: str) -> None:
        """Cache-only; `GraphStoreSink.record_page_finished` does the real write.
        Details: docs/dev/spiders/orchestration/graph_sink/tracker.md#mark_visited
        """
        self._visited_cache[page_url] = True
