"""The mechanical crawl loop's single-page interaction state machine.
Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#module
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from core.interfaces import PageState, VisitStep
from utils.urls import clean_url, route_shape
from ...content.component_matching import (
    component_identity,
    component_overlap_ratio,
    is_element_not_found,
    is_fillable,
)
from ..interaction_tracker import InteractionTracker
from .frontier import Frontier
from .outcomes import InteractionOutcomes
from .recovery import NavigationRecovery
from ..visit_result import ComponentInteraction, PageVisitResult

if TYPE_CHECKING:
    from ...browser.crawl4ai_crawler import Crawl4AICrawler
    from ..graph_sink import GraphStoreSink
    from ..mechanical_loop import MechanicalCrawlerConfig

# Circuit breaker for `visit`'s interaction loop - a session parked on a
# never-loading page. Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#_max_consecutive_unexplained_failures
_MAX_CONSECUTIVE_UNEXPLAINED_FAILURES = 3

# How many interactions between intra-visit progress lines. Silent below it,
# so an ordinary page says nothing. Above it, the loop has already done more
# work than any normal page needs, and since d59ce99 removed the per-page
# ceiling there is no longer anything that stops it - a page whose DOM keeps
# minting new component paths grows `frontier` from inside the loop that
# reads it (outcomes.py's frontier.append), so `while idx < len(frontier)`
# never ends. Printing the two numbers side by side is what makes that
# visible: a frontier growing as fast as idx is the signature.
# Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#_progress_every_n_interactions
_PROGRESS_EVERY_N_INTERACTIONS = 100


class PageVisitor:
    """Mechanically interacts with one page's frontier, called once per URL.
    Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#pagevisitor
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
        self.sink: Optional["GraphStoreSink"] = config.sink
        self.fill_value_fn = config.fill_value_fn
        self.state_transition_overlap_threshold = config.state_transition_overlap_threshold
        self.errors: List[ComponentInteraction] = []
        # Collaborators - see each module's own docstring for why it's
        # split out. Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#__init__-collaborators
        self._frontier = Frontier()
        self._recovery = NavigationRecovery(
            crawler, tracker, enqueue_url, enqueue_links, self.sink, self._frontier
        )
        self._outcomes = InteractionOutcomes(
            tracker, enqueue_url, enqueue_links, self.sink, self._frontier
        )
        self._enqueue = enqueue_url
        self._enqueue_links = enqueue_links
        # (page_key, component_identity) -> value already generated for that field.
        # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#_fill_value_cache
        self._fill_value_cache: Dict[tuple, str] = {}

    async def _fill_value(self, page_key: str, component: Dict[str, Any], page_description: str) -> str:
        """Reuse a previously generated value for the same field on this page.
        Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#_fill_value
        """
        key = (page_key, component_identity(component))
        if key in self._fill_value_cache:
            return self._fill_value_cache[key]
        value = await self.fill_value_fn(component, page_description)
        self._fill_value_cache[key] = value
        return value

    def _discovery_failed(self, url: str, exc: Exception) -> PageVisitResult:
        """Turn a `discover_page` exception into a normal (not interrupted)
        result instead of letting it propagate - one page's navigation
        failure (timeout, anti-bot block, ...) must not crash the worker
        that would otherwise keep draining the rest of the frontier.
        Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#_discovery_failed
        """
        print(f"Warning: could not discover {url!r}, skipping: {exc}")
        page_key = route_shape(url)
        failed = ComponentInteraction(page_key, path="", action="discover", error=str(exc))
        self.errors.append(failed)
        return PageVisitResult(url=page_key, resolved_url=url, components_discovered=0)

    async def visit(self, url: str, session_id: Optional[str] = None) -> PageVisitResult:  # noqa: C901
        """Visit `url` and mechanically interact with its frontier.
        `session_id` is the physical browser tab to reuse - a caller running
        several visits in sequence should pass the same one each time so
        crawl4ai navigates an existing tab instead of opening a new one.
        Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit
        """
        session_id = session_id or url
        # One sequence per pass. A local, not instance state: a single
        # PageVisitor is shared across concurrent workers, so a counter on
        # self would interleave two pages' steps into one nonsense trace.
        # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-step
        visit_step = VisitStep(visit_id=uuid4().hex[:12])
        try:
            state = await self.crawler.discover_page(url, session_id=session_id)
        except Exception as exc:
            return self._discovery_failed(url, exc)
        page_literal = clean_url(state.url)
        page_key = route_shape(state.url)

        if self.sink:
            await self.sink.record_page_arrival(page_key, description=state.description, title=state.title)
            await self.sink.record_inventory(page_key, state.components, state.links)
            await self.sink.record_text_content(page_key, state.text_content)
            # Only here, not on the post-interaction path below: those
            # requests already belong to the component that fired them.
            # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#record_page_network
            await self.sink.record_page_network(page_key, state.network_requests)
            await self.sink.record_page_metadata(page_key, state.metadata)

        self._enqueue_links(state.links)

        # Baseline snapshot for the next reveal's find_revealed_options diff.
        # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-known-components
        known_components: List[Dict[str, Any]] = state.components

        result = PageVisitResult(
            url=page_key,
            resolved_url=state.url,
            components_discovered=len(state.components),
            links_discovered=len(state.links),
        )

        # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-content-identity-exclusions
        frontier, seen_paths_this_pass = self._frontier.eligible(page_key, state.components, self.tracker)
        idx = 0

        # Three independent per-pass guards for the except-block below.
        # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-guards
        stale_resynced_since_success = False
        silent_navigation_checked_since_success = False
        consecutive_unexplained_failures = 0

        # No numeric ceiling - terminates via frontier exhaustion or a break
        # below, not a component/pass count. Details:
        # docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop
        while idx < len(frontier):
            component = frontier[idx]
            idx += 1
            if idx % _PROGRESS_EVERY_N_INTERACTIONS == 0:
                print(
                    f"  still on {page_key}: {idx} interactions, "
                    f"page frontier {len(frontier)}"
                )
            path = component["path"]
            if self.tracker.is_interacted(page_key, path):
                continue  # revealed again by an earlier interaction this pass, already handled

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
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-real-failure
                failed = ComponentInteraction(page_key, path, "fill" if fillable else "click", error=str(exc))
                self.errors.append(failed)
                result.interactions.append(failed)
                self.tracker.mark_interacted(page_key, path)  # don't retry a proven-broken target forever
                self._frontier.mark_interacted_identity(page_key, component)
                if self.sink:
                    await self.sink.record_interaction(
                        page_key, path, failed.action, value="", resulting_url="", step=visit_step.take()
                    )

                if is_element_not_found(exc) and not stale_resynced_since_success:
                    # Resync once and reconcile the rest of the frontier.
                    # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-stale-resync
                    stale_resynced_since_success = True
                    fresh_components = await self._recovery.recover_stale_frontier(
                        url, session_id, page_key, frontier, idx, result, seen_paths_this_pass
                    )
                    if fresh_components is not None:
                        known_components = fresh_components
                    continue

                # Counts toward the circuit breaker regardless of the check below.
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-not-element-not-found
                consecutive_unexplained_failures += 1

                if not silent_navigation_checked_since_success:
                    # Could mean the click DID navigate but timed out reporting it.
                    # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-silent-nav-check
                    silent_navigation_checked_since_success = True
                    if await self._recovery.handle_possible_silent_navigation(
                        url, session_id, page_key, page_literal, component, path, failed, result
                    ):
                        break

                if consecutive_unexplained_failures >= _MAX_CONSECUTIVE_UNEXPLAINED_FAILURES:
                    # Session likely dead - stop this pass, requeue for later.
                    # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-circuit-breaker-trip
                    result.interrupted_by_navigation = True
                    break
                continue

            stale_resynced_since_success = False
            silent_navigation_checked_since_success = False
            consecutive_unexplained_failures = 0
            self.tracker.mark_interacted(page_key, path)
            self._frontier.mark_interacted_identity(page_key, component)
            new_literal = clean_url(new_state.url)
            new_key = route_shape(new_state.url)
            interaction.resulting_url = new_literal
            result.interactions.append(interaction)
            if self.sink:
                # One position, shared by the interaction and the requests it
                # fired - that pairing is the whole point of stamping them.
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-step
                step = visit_step.take()
                await self.sink.record_interaction(
                    page_key, path, interaction.action, interaction.value, new_literal, step=step
                )
                if new_state.network_requests:
                    await self.sink.record_component_network(
                        page_key, path, new_state.network_requests, step=step
                    )

            if new_literal != page_literal:
                # Real physical navigation - must stop the pass regardless of page_key.
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-physical-navigation-branch
                await self._outcomes.handle_physical_navigation(
                    page_key, new_key, new_state, component, path, interaction, result
                )
                break
            elif component_overlap_ratio(known_components, new_state.components) < self.state_transition_overlap_threshold:
                # In-page state transition, not a mere reveal.
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-state-transition-branch
                page_key, frontier, seen_paths_this_pass = await self._outcomes.transition_to_new_state(
                    page_key, new_state, path, interaction.action, idx, len(frontier), known_components, result
                )
                known_components = new_state.components
                idx = 0
            else:
                # Same-URL DOM change - re-inventoried, not just mined for new items.
                # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-same-page-branch
                known_components = await self._outcomes.handle_same_page_reveal(
                    page_key, known_components, new_state, path, seen_paths_this_pass, frontier
                )

        if self.sink and not result.interrupted_by_navigation:
            # A navigation-interrupted pass must stay Pending, not be marked Finished here.
            # Details: docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-record-page-finished
            await self.sink.record_page_finished(page_key, len(known_components))
        return result
