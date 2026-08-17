"""Reconcile state after an ambiguous or failed interaction: a stale
selector, or a session that silently moved without reporting it.
Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#module
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

from core.interfaces import PageState
from utils.urls import clean_url, route_shape
from ...content.component_matching import remap_stale_frontier
from .frontier import Frontier
from ..visit_result import ComponentInteraction, PageVisitResult

if TYPE_CHECKING:
    from ...browser.crawl4ai_crawler import Crawl4AICrawler
    from ..graph_sink import GraphStoreSink
    from ..interaction_tracker import InteractionTracker


class NavigationRecovery:
    """Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#navigationrecovery"""

    def __init__(
        self,
        crawler: "Crawl4AICrawler",
        tracker: "InteractionTracker",
        enqueue_url: Callable[[str], None],
        enqueue_links: Callable[[List[Dict[str, str]]], None],
        sink: Optional["GraphStoreSink"],
        frontier_state: Frontier,
    ) -> None:
        self.crawler = crawler
        self.tracker = tracker
        self._enqueue = enqueue_url
        self._enqueue_links = enqueue_links
        self.sink = sink
        self.frontier_state = frontier_state

    async def _reconcile_frontier(
        self,
        page_key: str,
        frontier: List[Dict[str, Any]],
        idx: int,
        fresh_state: PageState,
        result: "PageVisitResult",
        seen_paths_this_pass: Set[str],
    ) -> None:
        """Shared second half of both recovery paths below: remap the
        remaining, not-yet-attempted frontier against a freshly-fetched DOM
        snapshot (however it was obtained - resync or a real navigation),
        record whatever the remap had to drop as a stale click, and replay
        the ordinary post-fetch bookkeeping (inventory + link enqueueing)
        `visit`'s own initial pass already does.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#_reconcile_frontier
        """
        frontier[idx:], dropped = remap_stale_frontier(frontier[idx:], fresh_state.components)
        for component in frontier[idx:]:
            seen_paths_this_pass.add(component.get("path"))
        for dropped_path in dropped:
            stale_interaction = ComponentInteraction(page_key, dropped_path, "click", stale=True)
            result.interactions.append(stale_interaction)
            self.tracker.mark_interacted(page_key, dropped_path)
            if self.sink:
                await self.sink.record_interaction(page_key, dropped_path, "click", value="", resulting_url="")

        if self.sink:
            await self.sink.record_inventory(page_key, fresh_state.components, fresh_state.links)
        self._enqueue_links(fresh_state.links)

    async def recover_stale_frontier(
        self,
        url: str,
        session_id: str,
        page_key: str,
        frontier: List[Dict[str, Any]],
        idx: int,
        result: "PageVisitResult",
        seen_paths_this_pass: Set[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Resync DOM state after "element not found" and remap the frontier.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#recover_stale_frontier
        """
        try:
            fresh_state = await self.crawler.resync(url, session_id)
        except Exception as resync_exc:
            print(f"Warning: stale-selector resync failed for {page_key!r}: {resync_exc}")
            return None
        await self._reconcile_frontier(page_key, frontier, idx, fresh_state, result, seen_paths_this_pass)
        return fresh_state.components

    async def return_to_origin(
        self,
        url: str,
        session_id: str,
        page_key: str,
        frontier: List[Dict[str, Any]],
        idx: int,
        result: "PageVisitResult",
        seen_paths_this_pass: Set[str],
    ) -> Optional[PageState]:
        """Navigate back to `url` after a mid-pass click landed on a
        destination this crawl already knows about, and reconcile the
        remaining frontier against the fresh DOM via the same
        `_reconcile_frontier` step `recover_stale_frontier` uses - a real
        navigation away and back can re-render selectors even when the
        page's own content hasn't changed.

        Returns the fresh `PageState` to become the pass's new baseline
        (`known_components`/`page_literal`), or `None` if the return
        navigation itself failed - the caller then has no live page left to
        keep interacting with and must fall back to the ordinary interrupted
        path (stop, requeue the origin for a later pass).
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#return_to_origin
        """
        try:
            fresh_state = await self.crawler.discover_page(url, session_id=session_id)
        except Exception as exc:
            print(f"Warning: could not return to {page_key!r} after a known-destination link: {exc}")
            return None
        await self._reconcile_frontier(page_key, frontier, idx, fresh_state, result, seen_paths_this_pass)
        return fresh_state

    async def check_for_silent_navigation(
        self, url: str, session_id: str, page_literal: str
    ) -> Optional[str]:
        """Check whether the live session moved despite an unclear failure.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#check_for_silent_navigation
        """
        try:
            current_state = await self.crawler.resync(url, session_id)
        except Exception as resync_exc:
            print(f"Warning: silent-navigation check failed for {page_literal!r}: {resync_exc}")
            return None
        current_literal = clean_url(current_state.url)
        return current_state.url if current_literal != page_literal else None

    async def handle_possible_silent_navigation(
        self,
        url: str,
        session_id: str,
        page_key: str,
        page_literal: str,
        component: Dict[str, Any],
        path: str,
        failed: "ComponentInteraction",
        result: "PageVisitResult",
    ) -> bool:
        """Check + bookkeeping for a possible silently-missed navigation.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#handle_possible_silent_navigation
        """
        silently_navigated_to = await self.check_for_silent_navigation(url, session_id, page_literal)
        if silently_navigated_to is None:
            return False
        self._enqueue(silently_navigated_to)
        result.interrupted_by_navigation = True
        self.frontier_state.mark_navigation_trigger(page_key, component)
        if self.sink:
            await self.sink.record_navigation_edge(page_key, route_shape(silently_navigated_to), path, failed.action)
        return True
