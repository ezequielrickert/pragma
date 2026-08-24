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
            await self.sink.record_inventory(
                page_key, self.frontier_state.canonicalize_inventory(page_key, fresh_state.components), fresh_state.links
            )
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
        page_literal: str,
        page_url: str,
        frontier: List[Dict[str, Any]],
        idx: int,
        result: "PageVisitResult",
        seen_paths_this_pass: Set[str],
    ) -> Optional[PageState]:
        """Step back to `page_literal` after a mid-pass click physically
        navigated away - known destination or not, see
        `docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation`
        for why this no longer branches on that - and reconcile the
        remaining frontier against the fresh DOM via the same
        `_reconcile_frontier` step `recover_stale_frontier` uses - a real
        navigation away and back can re-render selectors even when the
        page's own content hasn't changed.

        Uses `Crawl4AICrawler.go_back` (browser history, not a fresh
        `discover_page` navigation) - see that method's own docstring for
        why: this same page was just rendered a moment ago, so there is no
        need to make the target server render it again.

        Returns the fresh `PageState` to become the pass's new baseline
        (`known_components`/`page_literal`), or `None` if the return
        didn't land where expected even after `_reload_origin` below has
        had its own attempt. `go_back` itself raising is treated as fatal
        outright - a session that couldn't even execute `history.back()`
        is presumed dead, not worth a further request - but `go_back`
        returning cleanly on the wrong page (nothing left in this tab's
        history to go back to, or a client-side router swallowing the
        `popstate` event, e.g. a crashed SPA's error boundary that a route
        change alone doesn't clear) means the session is still alive, so a
        hard reload of `page_literal` is worth the one extra request
        before giving up on the pass entirely - see `_reload_origin`. Takes
        `page_url` (the origin's real, schemed URL, as opposed to
        `page_literal`'s stripped form) purely to hand to that fallback -
        `go_back` itself needs no navigable URL, only a live session.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#return_to_origin
        """
        try:
            fresh_state = await self.crawler.go_back(url, session_id)
        except Exception as exc:
            print(f"Warning: could not return to {page_key!r} after a known-destination link: {exc}")
            return None
        if clean_url(fresh_state.url) != page_literal:
            print(
                f"Warning: go_back landed on {fresh_state.url!r}, not {page_literal!r} - "
                f"reloading {page_key!r} directly before giving up."
            )
            fresh_state = await self._reload_origin(session_id, page_key, page_literal, page_url)
            if fresh_state is None:
                return None
        await self._reconcile_frontier(page_key, frontier, idx, fresh_state, result, seen_paths_this_pass)
        return fresh_state

    async def _reload_origin(
        self, session_id: str, page_key: str, page_literal: str, page_url: str
    ) -> Optional[PageState]:
        """`return_to_origin`'s last-resort fallback for a `go_back` that
        landed somewhere other than `page_literal`: a real `discover_page`
        navigation, deliberately not attempted as the first resort (see
        `return_to_origin`'s own docstring for why `go_back` alone is
        cheaper and the common case) but worth the one extra request once
        `go_back` has already proven history navigation alone won't get
        the session home - a crashed client-side router can strand a page
        on the wrong URL, or on the right URL but still rendering its
        error-boundary UI, in a way a route change alone can't clear.

        Navigates to `page_url` (the real, schemed URL) rather than
        `page_literal` (`clean_url`'s stripped form, kept only for the
        landing check below) - `discover_page` needs an actual navigable
        address.
        Details: docs/dev/spiders/orchestration/page_visitor/recovery.md#_reload_origin
        """
        try:
            fresh_state = await self.crawler.discover_page(page_url, session_id=session_id)
        except Exception as exc:
            print(f"Warning: reload fallback for {page_key!r} also failed: {exc}")
            return None
        if clean_url(fresh_state.url) != page_literal:
            print(
                f"Warning: reload fallback landed on {fresh_state.url!r}, not {page_literal!r} - "
                f"abandoning this pass for {page_key!r}."
            )
            return None
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
        if self.sink:
            await self.sink.record_navigation_edge(page_key, route_shape(silently_navigated_to), path, failed.action)
        return True
