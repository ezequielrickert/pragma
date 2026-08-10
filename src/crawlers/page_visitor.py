"""The mechanical crawl loop's single-page interaction state machine.
Details: docs/dev/crawlers/page_visitor.md#module
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set

from ..core.interfaces import PageState
from ..generators.component_classifier import find_revealed_options
from ..utils.urls import clean_url, route_shape
from .component_matching import (
    component_identity,
    component_overlap_ratio,
    is_element_not_found,
    is_fillable,
    remap_stale_frontier,
    state_transition_key,
)
from .interaction_tracker import InteractionTracker
from .visit_result import ComponentInteraction, PageVisitResult

if TYPE_CHECKING:
    from .crawl4ai_crawler import Crawl4AICrawler
    from .graph_sink import GraphStoreSink
    from .mechanical_loop import MechanicalCrawlerConfig

# Circuit breaker for `visit`'s interaction loop - a session parked on a
# never-loading page. Details: docs/dev/crawlers/page_visitor.md#_max_consecutive_unexplained_failures
_MAX_CONSECUTIVE_UNEXPLAINED_FAILURES = 3


class PageVisitor:
    """Mechanically interacts with one page's frontier, called once per URL.
    Details: docs/dev/crawlers/page_visitor.md#pagevisitor
    """

    def __init__(
        self,
        crawler: "Crawl4AICrawler",
        tracker: InteractionTracker,
        enqueue_url: Callable[[str], None],
        enqueue_links: Callable[[List[Dict[str, str]]], None],
        config: "MechanicalCrawlerConfig",
    ) -> None:
        self.crawler = crawler
        self.tracker = tracker
        self._enqueue = enqueue_url
        self._enqueue_links = enqueue_links
        self.sink: Optional["GraphStoreSink"] = config.sink
        self.fill_value_fn = config.fill_value_fn
        self.element_budget = config.element_budget
        self.max_passes_per_page = config.max_passes_per_page
        self.state_transition_overlap_threshold = config.state_transition_overlap_threshold
        self.errors: List[ComponentInteraction] = []
        # page_key -> identities proven to navigate away from that page.
        # Details: docs/dev/crawlers/page_visitor.md#_navigation_trigger_identities
        self._navigation_trigger_identities: Dict[str, Set[tuple]] = {}
        # page_key -> identities ever interacted with, regardless of path.
        # Details: docs/dev/crawlers/page_visitor.md#_interacted_identities
        self._interacted_identities: Dict[str, Set[tuple]] = {}
        # (page_key, component_identity) -> value already generated for that field.
        # Details: docs/dev/crawlers/page_visitor.md#_fill_value_cache
        self._fill_value_cache: Dict[tuple, str] = {}

    async def _recover_stale_frontier(
        self,
        url: str,
        session_id: str,
        page_key: str,
        frontier: List[Dict[str, Any]],
        idx: int,
        result: PageVisitResult,
        seen_paths_this_pass: Set[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Resync DOM state after "element not found" and remap the frontier.
        Details: docs/dev/crawlers/page_visitor.md#_recover_stale_frontier
        """
        try:
            fresh_state = await self.crawler.resync(url, session_id)
        except Exception as resync_exc:
            print(f"Warning: stale-selector resync failed for {page_key!r}: {resync_exc}")
            return None

        frontier[idx:], dropped = remap_stale_frontier(frontier[idx:], fresh_state.components)
        for component in frontier[idx:]:
            seen_paths_this_pass.add(component.get("path"))
        for dropped_path in dropped:
            stale_interaction = ComponentInteraction(page_key, dropped_path, "click", stale=True)
            result.interactions.append(stale_interaction)
            self.tracker.mark_interacted(page_key, dropped_path)
            if self.sink:
                self.sink.record_interaction(page_key, dropped_path, "click", value="", resulting_url="")

        if self.sink:
            self.sink.record_inventory(page_key, fresh_state.components, fresh_state.links)
        self._enqueue_links(fresh_state.links)
        return fresh_state.components

    async def _check_for_silent_navigation(
        self, url: str, session_id: str, page_literal: str
    ) -> Optional[str]:
        """Check whether the live session moved despite an unclear failure.
        Details: docs/dev/crawlers/page_visitor.md#_check_for_silent_navigation
        """
        try:
            current_state = await self.crawler.resync(url, session_id)
        except Exception as resync_exc:
            print(f"Warning: silent-navigation check failed for {page_literal!r}: {resync_exc}")
            return None
        current_literal = clean_url(current_state.url)
        return current_state.url if current_literal != page_literal else None

    async def _handle_possible_silent_navigation(
        self,
        url: str,
        session_id: str,
        page_key: str,
        page_literal: str,
        component: Dict[str, Any],
        path: str,
        failed: ComponentInteraction,
        result: PageVisitResult,
    ) -> bool:
        """Check + bookkeeping for a possible silently-missed navigation.
        Details: docs/dev/crawlers/page_visitor.md#_handle_possible_silent_navigation
        """
        silently_navigated_to = await self._check_for_silent_navigation(url, session_id, page_literal)
        if silently_navigated_to is None:
            return False
        self._enqueue(silently_navigated_to)
        result.interrupted_by_navigation = True
        self._navigation_trigger_identities.setdefault(page_key, set()).add(component_identity(component))
        if self.sink:
            self.sink.record_navigation_edge(page_key, route_shape(silently_navigated_to), path, failed.action)
        return True

    def _transition_to_new_state(
        self,
        page_key: str,
        new_state: PageState,
        path: str,
        action: str,
        idx: int,
        frontier_len: int,
        known_components: List[Dict[str, Any]],
        result: PageVisitResult,
    ) -> "tuple[str, List[Dict[str, Any]], Set[str]]":
        """Record + switch this pass onto an in-page SPA state transition.
        Details: docs/dev/crawlers/page_visitor.md#_transition_to_new_state
        """
        new_page_key = state_transition_key(page_key, new_state.components)
        result.state_transitions.append(new_page_key)
        if self.sink:
            self.sink.record_navigation_edge(page_key, new_page_key, path, action)
            # Old node is only "Finished" if this was its last frontier item.
            # Details: docs/dev/crawlers/page_visitor.md#_transition_to_new_state-finished-check
            if idx >= frontier_len:
                self.sink.record_page_finished(page_key, len(known_components))
            self.sink.record_page_arrival(
                new_page_key, description=new_state.description, title=new_state.title
            )
            self.sink.record_inventory(new_page_key, new_state.components, new_state.links)
            self.sink.record_text_content(new_page_key, new_state.text_content)
        self._enqueue_links(new_state.links)

        # Rebuilt like visit's own initial frontier, keyed to new_page_key.
        # Details: docs/dev/crawlers/page_visitor.md#_transition_to_new_state-frontier-rebuild
        new_page_nav_triggers = self._navigation_trigger_identities.get(new_page_key, set())
        new_page_interacted_identities = self._interacted_identities.get(new_page_key, set())
        frontier = [
            c for c in new_state.components
            if c.get("visible")
            and not self.tracker.is_interacted(new_page_key, c.get("path"))
            and component_identity(c) not in new_page_nav_triggers
            and component_identity(c) not in new_page_interacted_identities
        ]
        seen_paths_this_pass = {c.get("path") for c in frontier}
        return new_page_key, frontier, seen_paths_this_pass

    def _handle_physical_navigation(
        self,
        page_key: str,
        new_key: str,
        new_state: PageState,
        component: Dict[str, Any],
        path: str,
        interaction: ComponentInteraction,
        result: PageVisitResult,
    ) -> None:
        """Response to an interaction whose literal result URL differs from the page.
        Details: docs/dev/crawlers/page_visitor.md#_handle_physical_navigation
        """
        self._enqueue(new_state.url)
        result.interrupted_by_navigation = True
        # Remember this component's content identity as a proven one-way door.
        # Details: docs/dev/crawlers/page_visitor.md#_handle_physical_navigation-identity
        self._navigation_trigger_identities.setdefault(page_key, set()).add(component_identity(component))
        if self.sink:
            # A same-route_shape self-loop here is legitimate, not a bug.
            # Details: docs/dev/crawlers/page_visitor.md#_handle_physical_navigation-self-loop
            self.sink.record_navigation_edge(page_key, new_key, path, interaction.action)

    def _handle_same_page_reveal(
        self,
        page_key: str,
        known_components: List[Dict[str, Any]],
        new_state: PageState,
        path: str,
        seen_paths_this_pass: Set[str],
        frontier: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Response to an interaction that changed the DOM without navigating.
        Details: docs/dev/crawlers/page_visitor.md#_handle_same_page_reveal
        """
        if self.sink:
            self.sink.record_inventory(page_key, new_state.components, new_state.links)
        self._enqueue_links(new_state.links)

        # Attribute newly-revealed option-family components to the trigger.
        # Details: docs/dev/crawlers/page_visitor.md#_handle_same_page_reveal-revealed-options
        revealed = find_revealed_options(known_components, new_state.components)
        if self.sink and revealed:
            self.sink.record_revealed_options(page_key, path, revealed)

        # Append genuinely-new, visible, not-yet-interacted components.
        # Details: docs/dev/crawlers/page_visitor.md#_handle_same_page_reveal-append-frontier
        current_nav_triggers = self._navigation_trigger_identities.get(page_key, set())
        current_interacted_identities = self._interacted_identities.get(page_key, set())
        for candidate in new_state.components:
            cpath = candidate.get("path")
            if not candidate.get("visible"):
                continue
            if cpath in seen_paths_this_pass:
                continue
            if self.tracker.is_interacted(page_key, cpath):
                continue
            if component_identity(candidate) in current_nav_triggers:
                continue
            if component_identity(candidate) in current_interacted_identities:
                continue  # churning widget - see doc anchor above for the accepted tradeoff
            seen_paths_this_pass.add(cpath)
            frontier.append(candidate)

        return new_state.components

    async def _fill_value(self, page_key: str, component: Dict[str, Any], page_description: str) -> str:
        """Reuse a previously generated value for the same field on this page.
        Details: docs/dev/crawlers/page_visitor.md#_fill_value
        """
        key = (page_key, component_identity(component))
        if key in self._fill_value_cache:
            return self._fill_value_cache[key]
        value = await self.fill_value_fn(component, page_description)
        self._fill_value_cache[key] = value
        return value

    async def visit(self, url: str) -> PageVisitResult:
        """Visit `url` and mechanically interact with its frontier.
        Details: docs/dev/crawlers/page_visitor.md#visit
        """
        session_id = url
        state = await self.crawler.discover_page(url, session_id=session_id)
        page_literal = clean_url(state.url)
        page_key = route_shape(state.url)

        if self.sink:
            self.sink.record_page_arrival(page_key, description=state.description, title=state.title)
            self.sink.record_inventory(page_key, state.components, state.links)
            self.sink.record_text_content(page_key, state.text_content)

        self._enqueue_links(state.links)

        # Baseline snapshot for the next reveal's find_revealed_options diff.
        # Details: docs/dev/crawlers/page_visitor.md#visit-known-components
        known_components: List[Dict[str, Any]] = state.components

        result = PageVisitResult(
            url=page_key,
            resolved_url=state.url,
            components_discovered=len(state.components),
            links_discovered=len(state.links),
        )

        known_nav_triggers = self._navigation_trigger_identities.get(page_key, set())
        already_interacted_identities = self._interacted_identities.get(page_key, set())
        frontier: List[Dict[str, Any]] = [
            c for c in state.components
            if c.get("visible")
            and not self.tracker.is_interacted(page_key, c["path"])
            # Content-identity exclusions on top of the path-based one above.
            # Details: docs/dev/crawlers/page_visitor.md#visit-content-identity-exclusions
            and component_identity(c) not in known_nav_triggers
            and component_identity(c) not in already_interacted_identities
        ]
        seen_paths_this_pass: Set[str] = {c["path"] for c in frontier}
        idx = 0
        interactions_done = 0
        # element_budget * max_passes_per_page is the real per-visit ceiling.
        # Details: docs/dev/crawlers/page_visitor.md#visit-max-total-interactions
        max_total_interactions = self.element_budget * self.max_passes_per_page

        # Three independent per-pass guards for the except-block below.
        # Details: docs/dev/crawlers/page_visitor.md#visit-guards
        stale_resynced_since_success = False
        silent_navigation_checked_since_success = False
        consecutive_unexplained_failures = 0

        while idx < len(frontier) and interactions_done < max_total_interactions:
            component = frontier[idx]
            idx += 1
            path = component["path"]
            if self.tracker.is_interacted(page_key, path):
                continue  # revealed again by an earlier interaction this pass, already handled

            interactions_done += 1
            fillable = is_fillable(component)

            try:
                if fillable:
                    value = await self._fill_value(page_key, component, state.description)
                    new_state = await self.crawler.fill(url, session_id, path, value)
                    interaction = ComponentInteraction(page_key, path, "fill", value=value)
                else:
                    new_state = await self.crawler.click(url, session_id, path)
                    interaction = ComponentInteraction(page_key, path, "click")
            except Exception as exc:
                # Record distinctly, never treat as a silent no-op; keep going.
                # Details: docs/dev/crawlers/page_visitor.md#visit-except-real-failure
                failed = ComponentInteraction(page_key, path, "fill" if fillable else "click", error=str(exc))
                self.errors.append(failed)
                result.interactions.append(failed)
                self.tracker.mark_interacted(page_key, path)  # don't retry a proven-broken target forever
                self._interacted_identities.setdefault(page_key, set()).add(component_identity(component))
                if self.sink:
                    self.sink.record_interaction(page_key, path, failed.action, value="", resulting_url="")

                if is_element_not_found(exc) and not stale_resynced_since_success:
                    # Resync once and reconcile the rest of the frontier.
                    # Details: docs/dev/crawlers/page_visitor.md#visit-except-stale-resync
                    stale_resynced_since_success = True
                    fresh_components = await self._recover_stale_frontier(
                        url, session_id, page_key, frontier, idx, result, seen_paths_this_pass
                    )
                    if fresh_components is not None:
                        known_components = fresh_components
                    continue

                # Counts toward the circuit breaker regardless of the check below.
                # Details: docs/dev/crawlers/page_visitor.md#visit-except-not-element-not-found
                consecutive_unexplained_failures += 1

                if not silent_navigation_checked_since_success:
                    # Could mean the click DID navigate but timed out reporting it.
                    # Details: docs/dev/crawlers/page_visitor.md#visit-except-silent-nav-check
                    silent_navigation_checked_since_success = True
                    if await self._handle_possible_silent_navigation(
                        url, session_id, page_key, page_literal, component, path, failed, result
                    ):
                        break

                if consecutive_unexplained_failures >= _MAX_CONSECUTIVE_UNEXPLAINED_FAILURES:
                    # Session likely dead - stop this pass, requeue for later.
                    # Details: docs/dev/crawlers/page_visitor.md#visit-except-circuit-breaker-trip
                    result.interrupted_by_navigation = True
                    break
                continue

            stale_resynced_since_success = False
            silent_navigation_checked_since_success = False
            consecutive_unexplained_failures = 0
            self.tracker.mark_interacted(page_key, path)
            self._interacted_identities.setdefault(page_key, set()).add(component_identity(component))
            new_literal = clean_url(new_state.url)
            new_key = route_shape(new_state.url)
            interaction.resulting_url = new_literal
            result.interactions.append(interaction)
            if self.sink:
                self.sink.record_interaction(page_key, path, interaction.action, interaction.value, new_literal)
                if new_state.network_requests:
                    self.sink.record_component_network(page_key, path, new_state.network_requests)

            if new_literal != page_literal:
                # Real physical navigation - must stop the pass regardless of page_key.
                # Details: docs/dev/crawlers/page_visitor.md#visit-physical-navigation-branch
                self._handle_physical_navigation(page_key, new_key, new_state, component, path, interaction, result)
                break
            elif component_overlap_ratio(known_components, new_state.components) < self.state_transition_overlap_threshold:
                # In-page state transition, not a mere reveal.
                # Details: docs/dev/crawlers/page_visitor.md#visit-state-transition-branch
                page_key, frontier, seen_paths_this_pass = self._transition_to_new_state(
                    page_key, new_state, path, interaction.action, idx, len(frontier), known_components, result
                )
                known_components = new_state.components
                idx = 0
            else:
                # Same-URL DOM change - re-inventoried, not just mined for new items.
                # Details: docs/dev/crawlers/page_visitor.md#visit-same-page-branch
                known_components = self._handle_same_page_reveal(
                    page_key, known_components, new_state, path, seen_paths_this_pass, frontier
                )

        # True budget exhaustion only, not a navigation-interrupted pass.
        # Details: docs/dev/crawlers/page_visitor.md#visit-budget-exhausted
        result.budget_exhausted_with_frontier_remaining = (
            not result.interrupted_by_navigation and idx < len(frontier)
        )
        if self.sink and not result.interrupted_by_navigation and not result.budget_exhausted_with_frontier_remaining:
            # A cut-short pass must stay Pending, not be marked Finished here.
            # Details: docs/dev/crawlers/page_visitor.md#visit-record-page-finished
            self.sink.record_page_finished(page_key, len(known_components))
        return result
