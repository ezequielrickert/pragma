"""The slim per-page interaction step, per issue #236's design: replaces
the interaction half of the old `MechanicalCrawler`/`PageVisitor` combo
(`spiders/orchestration/mechanical_loop/`, `spiders/orchestration/
page_visitor/`) now that the URL frontier itself lives in
`PragmaDeepCrawlStrategy` (issue #239) instead. Standalone module, not yet
wired into any phase command - that wiring is issue #241's job.

Deliberately drops the old loop's recovery machinery (stale-element
resync, silent-navigation detection, in-page state-transition frontier
rebuild, return-to-origin after a physical navigation) rather than
porting it - a simplification decided with the user while charting this
ticket, not a crawl4ai-native replacement for any of it. What survives:
a component still gets its exact-reuse/family-sampler gate, its click or
fill, and a same-URL DOM reveal still gets mined for newly-visible
components - just without the old loop's multi-page recovery branches.

`Crawl4AICrawlerConfig.scan_full_page`/`flatten_shadow_dom` close the one
real content-completeness gap this ticket's research found (crawl4ai
never set either) - see that config's own docstring. Nothing here
"rebuilds" `click`/`fill` on `js_code`/`c4a_script`: checked
`crawl4ai.script.c4ai_script`'s own compiled JS (`_js_click`/`SET`)
directly, and both are a strict downgrade from what `Crawl4AICrawler`
already does - a synthetic `MouseEvent` never fires an element's default
action (link navigation, form submit) the way `element.click()` does,
and a plain `el.value = ...` assignment doesn't reach a React-controlled
input's native setter the way `fill()`'s property-descriptor dance does.
Issue #237 reached the same conclusion about `c4a_script` as a DSL; this
extends it to its underlying JS bodies too.
Details: docs/dev/spiders/orchestration/page_interaction/step.md#module
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

from core.data_contracts import PageState, VisitStep
from generators.component_classifier import find_revealed_options
from utils.urls import clean_url, resolve_href, route_shape
from ...content.component_matching import component_identity, is_fillable
from ..interaction_tracker import InteractionTracker
from ..visit_result import ComponentInteraction, PageVisitResult

if TYPE_CHECKING:
    from analysis.exact_reuse_index import ExactReuseIndex, ReuseEntry
    from analysis.family_sampling import FamilySampler
    from ...browser.crawl4ai_crawler import Crawl4AICrawler
    from ..graph_sink import GraphStoreSink

FillValueFn = Callable[[Dict[str, Any], str], Awaitable[str]]


def _blocked_summary(blocked_mutations: List[Dict[str, str]]) -> tuple:
    """`(blocked, blocked_reason)` for `sink.record_interaction` - identical
    to `page_visitor/visitor.py::_blocked_summary`, kept as its own copy
    here rather than a shared import since the module it lived in is what
    this one replaces.
    Details: docs/dev/spiders/orchestration/page_interaction/step.md#_blocked_summary
    """
    if not blocked_mutations:
        return False, ""
    methods = sorted({m["method"] for m in blocked_mutations})
    return True, ",".join(methods)


def _eligible(page_key: str, components: List[Dict[str, Any]], tracker: InteractionTracker) -> List[Dict[str, Any]]:
    """Visible, not-yet-interacted components from one `PageState` - the
    step's own starting frontier, and what a same-URL reveal appends to.
    Details: docs/dev/spiders/orchestration/page_interaction/step.md#_eligible
    """
    return [c for c in components if c.get("visible") and not tracker.is_interacted(page_key, c.get("path"))]


class PageInteractionStep:
    """Interacts with one `PageState`'s components, gated by exact-reuse
    and family-sampler membership - the small step issue #236 replaces
    `MechanicalCrawler`'s frontier-owning `PageVisitor` with.
    Details: docs/dev/spiders/orchestration/page_interaction/step.md#pageinteractionstep
    """

    def __init__(
        self,
        crawler: "Crawl4AICrawler",
        tracker: InteractionTracker,
        fill_value_fn: FillValueFn,
        exact_reuse_index: Optional["ExactReuseIndex"] = None,
        family_sampler: Optional["FamilySampler"] = None,
        sink: Optional["GraphStoreSink"] = None,
        is_known_url: Callable[[str], bool] = lambda url: False,
    ) -> None:
        self.crawler = crawler
        self.tracker = tracker
        self.fill_value_fn = fill_value_fn
        self._exact_reuse_index = exact_reuse_index
        self._family_sampler = family_sampler
        self.sink = sink
        self._is_known = is_known_url
        # (page_key, component_identity) -> value already generated for that field.
        # Details: docs/dev/spiders/orchestration/page_interaction/step.md#_fill_value_cache
        self._fill_value_cache: Dict[tuple, str] = {}
        # page_key -> {identity: the path it was first recorded under} - a
        # same-page reveal can compute a different nth-of-type path for a
        # component this page already recorded (issue #170); pinning it
        # here keeps the graph store's path-keyed HAS_COMPONENT edge
        # singular. Relocated unchanged from `page_visitor/frontier.py::
        # Frontier.canonicalize_inventory`.
        # Details: docs/dev/spiders/orchestration/page_interaction/step.md#_canonical_paths
        self._canonical_paths: Dict[str, Dict[tuple, str]] = {}

    def canonicalize_inventory(self, page_key: str, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """`components`, each pinned to its content identity's first-seen
        path on `page_key` - what every `record_inventory` call gets,
        while callers still act on a component's own live `path`. Public:
        the engine core's own initial-discovery `record_inventory` call
        (issue #241) has to canonicalize through the same map this step
        later reveals against, or a same-URL reveal's canonicalization
        would establish different canonical paths than the initial write
        did (issue #170).
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#canonicalize_inventory
        """
        canonical = self._canonical_paths.setdefault(page_key, {})
        return [
            {**c, "path": canonical.setdefault(component_identity(c), c.get("path", ""))}
            for c in components
        ]

    async def _fill_value(self, page_key: str, component: Dict[str, Any], page_description: str) -> str:
        """Reuse a previously generated value for the same field on this page.
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#_fill_value
        """
        key = (page_key, component_identity(component))
        if key in self._fill_value_cache:
            return self._fill_value_cache[key]
        value = await self.fill_value_fn(component, page_description)
        self._fill_value_cache[key] = value
        return value

    def _reuse_gate(
        self, page_key: str, path: str, component: Dict[str, Any]
    ) -> "Optional[ReuseEntry | str]":
        """Exact-reuse-index check, relocated unchanged from `PageVisitor.
        _drain_interaction_frontier` - returns the `ReuseEntry` to claim
        (already flipped `interacted=True`, same synchronous-claim
        reasoning as before), or `"skip"` when this exact canonical
        component was already interacted with elsewhere.
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#_reuse_gate
        """
        if self._exact_reuse_index is None:
            return None
        entry = self._exact_reuse_index.lookup(page_key, component)
        if entry is None:
            return None
        if entry.interacted:
            self._exact_reuse_index.skipped.append((page_key, path))
            return "skip"
        entry.interacted = True
        return entry

    async def _skip_known_link(self, page_key: str, target_key: str, path: str) -> None:
        """A static `<a href>` whose destination this crawl already knows -
        record the edge without spending a real click on it. Relocated
        unchanged from `InteractionOutcomes.skip_known_link`.
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#_skip_known_link
        """
        if self.sink:
            await self.sink.record_navigation_edge(page_key, target_key, path, "click")

    async def _record_reveal(
        self, page_key: str, path: str, known: List[Dict[str, Any]], new_state: PageState
    ) -> None:
        """Sink writes for a same-URL DOM reveal - inventory (canonicalized
        by the caller before this runs) and revealed-option attribution.
        Relocated from `InteractionOutcomes.handle_same_page_reveal`, minus
        the frontier append (the caller owns that, since it also owns idx).
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#_record_reveal
        """
        from generators.component_classifier import find_revealed_options

        if not self.sink:
            return
        await self.sink.record_inventory(
            page_key, self.canonicalize_inventory(page_key, new_state.components), new_state.links
        )
        revealed = find_revealed_options(known, new_state.components)
        if revealed:
            await self.sink.record_revealed_options(page_key, path, revealed)

    async def interact(self, url: str, session_id: str, state: PageState) -> PageVisitResult:
        """Click/fill every eligible component in `state`, one `PageState`
        (`discover_page`'s or a prior `interact()`'s result) at a time - no
        multi-page recovery, no requeue: a physical navigation or an
        unexplained failure just ends this pass, per this ticket's own
        simplification decision. `page_key`/`page_url` are both derived
        from `state.url` - `url` is only the crawl4ai session's own
        navigation target, kept separate since a redirect can leave it
        differing from `state.url`.
        Details: docs/dev/spiders/orchestration/page_interaction/step.md#interact
        """
        page_key = route_shape(state.url)
        page_url = state.url
        result = PageVisitResult(
            url=page_key, resolved_url=state.url,
            components_discovered=len(state.components), links_discovered=len(state.links),
        )
        visit_step = VisitStep(visit_id=uuid4().hex[:12])
        page_literal = clean_url(state.url)
        known_components = state.components
        frontier = _eligible(page_key, state.components, self.tracker)
        seen_paths = {c.get("path") for c in frontier}
        idx = 0

        while idx < len(frontier):
            component = frontier[idx]
            idx += 1
            path = component["path"]
            if self.tracker.is_interacted(page_key, path):
                continue

            reuse_entry = self._reuse_gate(page_key, path, component)
            if reuse_entry == "skip":
                self.tracker.mark_interacted(page_key, path)
                continue

            if self._family_sampler and not self._family_sampler.should_interact(page_key, component):
                self.tracker.mark_interacted(page_key, path)
                continue

            fillable = is_fillable(component)
            if not fillable:
                href = component.get("attributes", {}).get("href", "")
                target_url = resolve_href(page_url, href)
                if target_url is not None and self._is_known(target_url):
                    await self._skip_known_link(page_key, route_shape(target_url), path)
                    self.tracker.mark_interacted(page_key, path)
                    continue

            try:
                if fillable:
                    value = await self._fill_value(page_key, component, state.description)
                    new_state = await self.crawler.fill(url, session_id, path, value)
                    interaction = ComponentInteraction(page_key, path, "fill", value=value)
                else:
                    new_state = await self.crawler.click(url, session_id, path)
                    interaction = ComponentInteraction(page_key, path, "click")
            except Exception as exc:
                failed = ComponentInteraction(page_key, path, "fill" if fillable else "click", error=str(exc))
                result.interactions.append(failed)
                self.tracker.mark_interacted(page_key, path)
                if self.sink:
                    await self.sink.record_interaction(
                        page_key, path, failed.action, value="", resulting_url="", step=visit_step.take()
                    )
                continue

            self.tracker.mark_interacted(page_key, path)
            new_literal = clean_url(new_state.url)
            new_key = route_shape(new_state.url)
            interaction.resulting_url = new_literal
            result.interactions.append(interaction)
            if self.sink:
                step = visit_step.take()
                blocked, blocked_reason = _blocked_summary(new_state.blocked_mutations)
                await self.sink.record_interaction(
                    page_key, path, interaction.action, interaction.value, new_literal, step=step,
                    blocked=blocked, blocked_reason=blocked_reason,
                )
                if new_state.network_requests:
                    await self.sink.record_component_network(page_key, path, new_state.network_requests, step=step)

            if new_literal != page_literal:
                # Physical navigation - recorded, then this pass ends here.
                # No return-to-origin: whatever else this page still owed a
                # click is left for a later, separate visit of it.
                if self.sink:
                    await self.sink.record_navigation_edge(page_key, new_key, path, interaction.action)
                    # Never "skip" here - that case already `continue`d above.
                    if reuse_entry is not None:
                        for sibling_key, sibling_path in reuse_entry.siblings_of((page_key, path)):
                            await self.sink.record_navigation_edge(sibling_key, new_key, sibling_path, interaction.action)
                result.interrupted_by_navigation = True
                break

            # Same-URL DOM reveal - mine it for newly-visible components.
            await self._record_reveal(page_key, path, known_components, new_state)
            known_components = new_state.components
            for candidate in new_state.components:
                cpath = candidate.get("path")
                if not candidate.get("visible") or cpath in seen_paths or self.tracker.is_interacted(page_key, cpath):
                    continue
                seen_paths.add(cpath)
                frontier.append(candidate)

        if self.sink and not result.interrupted_by_navigation:
            await self.sink.record_page_finished(page_key, len(known_components))
        return result
