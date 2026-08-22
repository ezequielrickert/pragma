"""What bookkeeping follows each of the three ways a successful
interaction can change page state: a real physical navigation, an
in-page SPA state transition, or a same-URL DOM reveal.
Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#module
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from analysis.exact_reuse_index import ReuseEntry
from core.interfaces import PageState
from generators.component_classifier import find_revealed_options
from ...content.component_matching import state_transition_key
from .frontier import Frontier

if TYPE_CHECKING:
    from ..graph_sink import GraphStoreSink
    from ..interaction_tracker import InteractionTracker
    from ..visit_result import ComponentInteraction, PageVisitResult


class InteractionOutcomes:
    """Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#interactionoutcomes"""

    def __init__(
        self,
        tracker: "InteractionTracker",
        enqueue_url: Callable[[str], None],
        enqueue_links: Callable[[List[Dict[str, str]]], None],
        sink: Optional["GraphStoreSink"],
        frontier_state: Frontier,
        is_known_url: Callable[[str], bool],
    ) -> None:
        self.tracker = tracker
        self._enqueue = enqueue_url
        self._enqueue_links = enqueue_links
        self.sink = sink
        self.frontier_state = frontier_state
        self._is_known = is_known_url

    async def transition_to_new_state(
        self,
        page_key: str,
        new_state: PageState,
        path: str,
        action: str,
        idx: int,
        frontier_len: int,
        known_components: List[Dict[str, Any]],
        result: "PageVisitResult",
    ) -> Tuple[str, List[Dict[str, Any]], Set[str]]:
        """Record + switch this pass onto an in-page SPA state transition.
        Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#transition_to_new_state
        """
        new_page_key = state_transition_key(page_key, new_state.components)
        result.state_transitions.append(new_page_key)
        if self.sink:
            await self.sink.record_navigation_edge(page_key, new_page_key, path, action)
            # Old node is only "Finished" if this was its last frontier item.
            # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#transition_to_new_state-finished-check
            if idx >= frontier_len:
                await self.sink.record_page_finished(page_key, len(known_components))
            await self.sink.record_page_arrival(
                new_page_key, description=new_state.description, title=new_state.title
            )
            await self.sink.record_inventory(new_page_key, new_state.components, new_state.links)
            await self.sink.record_text_content(new_page_key, new_state.text_content)
            await self.sink.record_state_styles(new_page_key, new_state.pseudo_styles)
        self._enqueue_links(new_state.links)

        # Rebuilt like visit's own initial frontier, keyed to new_page_key.
        # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#transition_to_new_state-frontier-rebuild
        frontier, seen_paths_this_pass = self.frontier_state.eligible(new_page_key, new_state.components, self.tracker)
        return new_page_key, frontier, seen_paths_this_pass

    async def skip_known_link(
        self, page_key: str, target_key: str, component: Dict[str, Any], path: str
    ) -> None:
        """Record a static `<a href>` component's destination without ever
        clicking it - its raw `href` attribute resolved (via
        `docs/dev/utils/urls.md#resolve_href`) to a destination already
        known to this crawl, so there's nothing a real click would
        discover that this doesn't already assert, and clicking it would
        cost a real browser navigation (and everything that can go wrong
        with one - anti-bot false positives, target load, a failed
        `return_to_origin`) for no new information.

        Same edge-recording and identity-exclusion bookkeeping
        `handle_physical_navigation` does for a *followed* known-
        destination link - deliberately does not touch `tracker`/append to
        `result.interactions`, though: `visit`'s caller does that (same as
        every other skipped-without-attempting component), since no click
        actually happened here to record.
        Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#skip_known_link
        """
        self.frontier_state.mark_navigation_trigger(component)
        if self.sink:
            await self.sink.record_navigation_edge(page_key, target_key, path, "click")

    async def handle_physical_navigation(
        self,
        page_key: str,
        new_key: str,
        new_state: PageState,
        component: Dict[str, Any],
        path: str,
        interaction: "ComponentInteraction",
        result: "PageVisitResult",
        reuse_entry: Optional[ReuseEntry] = None,
    ) -> None:
        """Bookkeeping for an interaction whose literal result URL differs
        from the page - always records the edge and excludes the component
        from future frontier builds on this page (a proven one-way door
        either way), and enqueues the destination for its own separate
        future visit when it isn't already known to this crawl (queued, in
        flight, or visited) - a known destination needs no separate entry,
        it's already accounted for.

        `reuse_entry` is this component's `ExactReuseIndex` entry, when it
        has one - the real navigation edge just recorded is also inferred
        onto every other page rendering the same canonical component
        (issue #140), sparing them a live click of their own on the
        strength of it being the same node, not a merely similar one.

        Never decides whether the pass has to stop: `visit` always follows
        this with `return_to_origin` to hop the browser back and keep
        draining this page's own frontier, regardless of whether the
        destination was known - `return_to_origin`'s own failure fallback
        (falling back to `result.interrupted_by_navigation = True`) is what
        actually handles a genuinely unrecoverable session, not a decision
        made here.
        Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation
        """
        # Remember this component's content identity as a proven one-way door.
        # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation-identity
        self.frontier_state.mark_navigation_trigger(component)
        if self.sink:
            # A same-route_shape self-loop here is legitimate, not a bug.
            # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation-self-loop
            await self.sink.record_navigation_edge(page_key, new_key, path, interaction.action)
            if reuse_entry is not None:
                for sibling_key, sibling_path in reuse_entry.siblings_of((page_key, path)):
                    await self.sink.record_navigation_edge(
                        sibling_key, new_key, sibling_path, interaction.action
                    )
        if not self._is_known(new_state.url):
            self._enqueue(new_state.url)

    async def handle_same_page_reveal(
        self,
        page_key: str,
        known_components: List[Dict[str, Any]],
        new_state: PageState,
        path: str,
        seen_paths_this_pass: Set[str],
        frontier: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Response to an interaction that changed the DOM without navigating.
        Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_same_page_reveal
        """
        if self.sink:
            await self.sink.record_inventory(page_key, new_state.components, new_state.links)
        self._enqueue_links(new_state.links)

        # Attribute newly-revealed option-family components to the trigger.
        # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_same_page_reveal-revealed-options
        revealed = find_revealed_options(known_components, new_state.components)
        if self.sink and revealed:
            await self.sink.record_revealed_options(page_key, path, revealed)

        # Append genuinely-new, visible, not-yet-interacted components.
        # Details: docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_same_page_reveal-append-frontier
        for candidate in new_state.components:
            cpath = candidate.get("path")
            if not candidate.get("visible"):
                continue
            if cpath in seen_paths_this_pass:
                continue
            if self.tracker.is_interacted(page_key, cpath):
                continue
            if self.frontier_state.is_excluded(page_key, candidate):
                continue  # churning widget - see doc anchor above for the accepted tradeoff
            seen_paths_this_pass.add(cpath)
            frontier.append(candidate)

        return new_state.components
