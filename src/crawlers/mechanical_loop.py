"""Phase 2 of the crawl4ai migration: the mechanical, exhaustive-but-bounded
interaction loop that replaces the old per-step LLM decision loop
(`SimplePRDGenerator._execute_loop`). Fill values default to a deterministic
placeholder (`fill_values.default_placeholder_fill_value`) but accept a real
AI-backed one (`fill_value_agent.make_ai_fill_value_fn`, Phase 4) via the
`fill_value_fn` constructor param - the only AI call in the crawl itself,
everything else the migration adds is post-hoc (Phase 5). Page/component
state is tracked in-memory by default (`InMemoryInteractionTracker`) or via
`GraphStore` when a `sink` is supplied (Phase 3, `graph_sink.py`).

Two frontiers, composed but never conflated (per the plan):
- **URL frontier**: a plain FIFO queue of discovered-but-not-visited URLs,
  fed by every page's extracted links. No model decision needed - visited in
  deterministic discovery order.
- **Component/interaction frontier**: per page, every *visible*, not-yet-
  interacted-with component, capped by `element_budget` per page (the
  backstop against a pathological reveal-chain, not a normal-case limiter -
  default generous). A click/fill that changes the DOM on the *same* URL gets
  its newly-revealed components appended to the same pass's frontier (still
  budget-capped); a click/fill that navigates to a *different* URL gets that
  URL queued onto the URL frontier instead of being followed inline - avoiding
  a depth-first recursive blowup is the whole reason interaction and
  navigation are handled as two separate frontiers rather than one.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Set

from ..core.interfaces import PageState
from ..generators.component_classifier import find_revealed_options
from ..utils.urls import clean_url, is_in_scope, route_shape
from .crawl4ai_crawler import Crawl4AICrawler
from .fill_values import default_placeholder_fill_value
from .graph_sink import GraphStoreInteractionTracker, GraphStoreSink

# Component tags/input_types the mechanical loop treats as "type into", not
# "click" - matches PlaywrightScraper's own fill() target shape (a text-like
# input, a textarea, or a select). Checkbox/radio/button-typed inputs are
# click targets even though they're <input> tags.
_FILLABLE_INPUT_TYPES = {"", "text", "email", "search", "tel", "url", "number", "password"}


def _is_element_not_found(exc: Exception) -> bool:
    """Whether `exc` is specifically the "selector didn't resolve to a live
    element" failure `crawl4ai_crawler.py`'s click()/fill() raise (message
    literally contains "element not found") - as opposed to some other
    interaction failure (a JS exception, a network issue). Only this specific
    case triggers the stale-selector resync below: an id-based `path` that no
    longer matches anything is the one failure mode a fresh same-URL
    re-discovery can actually recover from; other failures get no special
    handling and fall through to the existing record-and-continue behavior.
    """
    return "element not found" in str(exc).lower()


def _component_identity(component: Dict[str, Any]) -> tuple:
    """Content-based identity for a component - stable across a DOM
    remount that reassigns ids (hence `path`) but leaves what the element
    actually *is* unchanged. Deliberately doesn't include `path`/`attributes.
    id` (the very thing a remount invalidates) or `rect` (position can shift
    for unrelated layout reasons); `(tag, role, name, form, text)` is already
    what `discover_components.js` extracts for every component, so this needs
    no new discovery data.
    """
    return (
        component.get("tag", ""),
        component.get("role", ""),
        component.get("name", ""),
        component.get("form", ""),
        component.get("text", ""),
    )


def _component_signature(components: List[Dict[str, Any]]) -> str:
    """Stable, order-independent fingerprint of a component snapshot's
    *shape* - a short hash of the sorted set of `_component_identity()`
    tuples for every *visible* component. Used to derive a `state_key` for
    an in-page SPA state transition (see `_visit_page`'s "Same-URL DOM
    change" branch): two visits that land on the same underlying screen
    (e.g. re-crawling the same "start order" transition from a fresh
    session) produce the same signature and collapse to the same graph
    node - the same "canonical identity, not a raw counter" discipline
    `route_shape()` already applies to session-token URLs (see
    wiki/graph-based-crawl-tracking.md).
    """
    identities = sorted(_component_identity(c) for c in components if c.get("visible"))
    return hashlib.sha1(repr(identities).encode("utf-8")).hexdigest()[:10]


def _state_transition_key(page_key: str, components: List[Dict[str, Any]]) -> str:
    """Canonical GraphStore/tracker key for an in-page state reached without
    any URL change - see `_component_signature`."""
    return f"{page_key}#state:{_component_signature(components)}"


def _component_overlap_ratio(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> float:
    """Fraction of `before`'s *visible* components (by content identity,
    `_component_identity`) that still exist in `after`. This is the signal
    `_visit_page` uses to tell an ordinary same-page *reveal* (a dropdown
    opens - nearly everything from `before` is still there, plus a few new
    items) apart from a genuine in-page *state transition* (the whole
    screen was replaced - almost nothing from `before` survives).

    Confirmed live on empanad.app (see debug_logs/): clicking "start order"
    never navigates (`navigated: False` throughout) but the component count
    swings 3 -> 26 -> 0 -> 11 across one session, and the saved page
    markdown collapses to near-nothing mid-pass - a full-screen replace, not
    a widget opening. The pre-existing "same-URL DOM change" handling
    assumes the *reveal* shape (find_revealed_options, append-to-frontier);
    treating a full-screen replace the same way would merge several
    human-distinguishable screens into one graph node's component ledger,
    indistinguishable in the final PRD from a page that never changed.

    Returns 1.0 (never a transition) when `before` has no visible components
    to compare against - a vacuous "before" snapshot is not itself evidence
    of a transition, and this project's decline-not-override discipline
    (wiki/graph-based-crawl-tracking.md) says a weak/absent signal should
    never trigger the riskier branch.
    """
    before_identities = {_component_identity(c) for c in before if c.get("visible")}
    if not before_identities:
        return 1.0
    after_identities = {_component_identity(c) for c in after if c.get("visible")}
    return len(before_identities & after_identities) / len(before_identities)


def _remap_stale_frontier(
    remaining: List[Dict[str, Any]], fresh_components: List[Dict[str, Any]]
) -> "tuple[List[Dict[str, Any]], List[str]]":
    """Reconcile `remaining` (not-yet-attempted frontier items, built from a
    now-possibly-stale snapshot) against `fresh_components` (a just-resynced,
    authoritative snapshot of the current DOM) after an "element not found"
    failure - see `_visit_page`'s except-block docstring for when this runs.

    Three outcomes per remaining item:
    - Its `path` still resolves in the fresh snapshot (untouched by whatever
      remounted) - kept as-is.
    - Its `path` doesn't, but a component with the same content identity
      (`_component_identity`) does - very likely the same logical element
      under a reassigned id; kept with `path` swapped to the fresh one.
    - Neither - genuinely gone (removed from the page, or no longer visible
      in a way this snapshot would show); dropped, and its path returned
      separately so the caller can record it as `stale`, not silently lose
      it.
    """
    fresh_paths = {c.get("path") for c in fresh_components}
    identity_map: Dict[tuple, str] = {}
    for c in fresh_components:
        identity_map.setdefault(_component_identity(c), c.get("path"))

    remapped: List[Dict[str, Any]] = []
    dropped: List[str] = []
    for component in remaining:
        path = component.get("path")
        if path in fresh_paths:
            remapped.append(component)
            continue
        new_path = identity_map.get(_component_identity(component))
        if new_path:
            updated = dict(component)
            updated["path"] = new_path
            remapped.append(updated)
        else:
            dropped.append(path)
    return remapped, dropped


def _is_fillable(component: Dict[str, Any]) -> bool:
    tag = component.get("tag", "")
    if tag == "textarea":
        return True
    if tag == "select":
        return True
    if tag == "input":
        return component.get("input_type", "") in _FILLABLE_INPUT_TYPES
    return False


class InteractionTracker(Protocol):
    """Consult-before-act seam (wiki/graph-based-crawl-tracking.md's "the
    ledger must be consulted, not write-only," reapplied to a mechanical loop
    with no per-step model decision to guard). `InMemoryInteractionTracker`
    is Phase 2's default; Phase 3 swaps in a `GraphStore`-backed
    implementation so the same accurate-frontier property holds across a
    persisted multi-run crawl, not just within one process.
    """

    def is_interacted(self, page_url: str, path: str) -> bool: ...

    def mark_interacted(self, page_url: str, path: str) -> None: ...

    def is_visited(self, page_url: str) -> bool: ...

    def mark_visited(self, page_url: str) -> None: ...


class InMemoryInteractionTracker:
    """Process-local `InteractionTracker` - everything lost on exit, same
    caveat `InMemoryGraphStore` already documents. Fine for Phase 2's
    standalone validation; not meant to survive into Phase 3+.
    """

    def __init__(self) -> None:
        self._interacted: Dict[str, Set[str]] = {}
        self._visited: Set[str] = set()

    def is_interacted(self, page_url: str, path: str) -> bool:
        return path in self._interacted.get(page_url, set())

    def mark_interacted(self, page_url: str, path: str) -> None:
        self._interacted.setdefault(page_url, set()).add(path)

    def is_visited(self, page_url: str) -> bool:
        return page_url in self._visited

    def mark_visited(self, page_url: str) -> None:
        self._visited.add(page_url)


@dataclass
class ComponentInteraction:
    page_url: str
    path: str
    action: str  # "click" | "fill"
    value: str = ""
    resulting_url: str = ""
    error: Optional[str] = None
    # True when this entry represents a frontier item dropped by
    # `_remap_stale_frontier` (an "element not found" failure, resynced, and
    # still not resolvable by content identity) rather than a real attempted-
    # and-failed interaction. Kept distinct from `error` so a human/consumer
    # reading `errors`/`page_results` can tell "we tried and the site
    # rejected it" apart from "a DOM remount stranded this component and we
    # gave up looking for it in this pass" - same "don't silently lose it"
    # discipline as `interrupted_by_navigation`.
    stale: bool = False


@dataclass
class PageVisitResult:
    url: str
    components_discovered: int
    interactions: List[ComponentInteraction] = field(default_factory=list)
    links_discovered: int = 0
    budget_exhausted_with_frontier_remaining: bool = False
    # The literal, already-redirect-resolved URL this visit actually landed
    # on (`state.url` from Crawl4AICrawler.discover_page - see its
    # `_resolved_url` for why this can differ from the URL requested).
    # Deliberately NOT `url` above (which is the *canonical*, route_shape()-
    # collapsed storage key - see `_visit_page`'s docstring) and NOT
    # necessarily identical to whatever literal string this visit was
    # originally requested with either. This is what a follow-up-pass
    # requeue must re-request - see `interrupted_by_navigation`'s docstring
    # for why re-requesting the *original* literal string is a real bug on a
    # redirecting entry point.
    resolved_url: str = ""
    # True when a click/fill mid-pass navigated the session's page away from
    # `url` before the frontier was drained - see `_visit_page`'s docstring
    # for why the pass stops immediately rather than continuing to act
    # against selectors that belonged to a page the session has physically
    # left. `crawl_site`/`_worker` re-queue `resolved_url` (not the original
    # request) when this is set, so the untouched remainder of the frontier
    # gets a follow-up pass (already-interacted components, including the one
    # that caused the navigation, are skipped via the tracker next time -
    # guaranteed forward progress each pass).
    #
    # **Bug found live on empanad.app, fixed by requeuing `resolved_url`
    # instead of the original request**: the site's *bare* entry URL
    # (`https://empanad.app`) redirects to a brand-new `/o/<hash>` session on
    # *every* visit - not just the first. Re-queuing the originally-requested
    # literal string (the bare URL) for a follow-up pass meant every such
    # pass re-triggered a fresh redirect to yet another new hash instead of
    # returning to the order the first pass was actually working on -
    # confirmed in a real debug log: a follow-up pass's `before_goto` request
    # for the literal bare URL landed on a third, completely different order
    # hash, abandoning the second hash's own still-undrained frontier
    # entirely. `resolved_url` is what `discover_page` actually landed on
    # after any redirect the *first* time - re-requesting that directly
    # (a concrete, addressable resource, not a redirecting entry point) is
    # what actually returns to the same session/order instead of minting
    # another new one. For an ordinary, non-redirecting site, `resolved_url`
    # is identical to what was requested, so this is a no-op there.
    interrupted_by_navigation: bool = False
    # Every `state_key` (see `_state_transition_key`) this pass switched onto
    # after detecting an in-page SPA state transition (low component overlap
    # on a same-URL DOM change - see `_component_overlap_ratio`). `url`
    # above stays the *first* node this visit started on; this records every
    # subsequent node reached within the same continuous session, in order.
    # Empty for the overwhelming majority of pages (ordinary sites, and
    # SPAs whose same-page changes are ordinary reveals) - only populated
    # when a real screen-replacement was detected.
    state_transitions: List[str] = field(default_factory=list)


class MechanicalCrawler:
    """Drives `Crawl4AICrawler` through a full site crawl with no per-step AI
    decision: every page reachable via links gets visited, every visible
    not-yet-interacted component on each page gets clicked or filled, up to
    `element_budget` interactions per page per pass.

    `page_concurrency` (default 1) controls how many pages get visited at
    once - `crawl_site` runs that many `_worker()` tasks pulling from a
    shared `asyncio.Queue` URL frontier instead of one sequential loop.
    Default 1 preserves the original fully-sequential behavior exactly (one
    worker, same visit order, same guarantees). Raising it is the only lever
    that actually gets a large crawl's wall-clock time down from hours to
    minutes: every fixed per-interaction wait
    (`Crawl4AICrawler.wait_seconds`/`interaction_wait_seconds`) overlaps
    across concurrently-visited pages instead of serializing - confirmed via
    a real run's own debug log that those fixed sleeps, not rendering or
    network cost, dominate a sequential crawl's time.

    What raising `page_concurrency` changes, precisely:
    - `max_pages` becomes a *soft* bound - concurrent workers can each pass
      the "have I hit the cap" check before either increments the shared
      counter, so the crawl can overshoot by up to `page_concurrency - 1`
      pages. Same "documented, deliberate looseness" as `element_budget`/
      `max_passes_per_page` elsewhere in this class - not worth a lock for a
      backstop that was never meant to be exact.
    - Each concurrently-visited page still gets its own `session_id` (see
      `_visit_page` - `session_id = url`, one per literal page, unchanged),
      so concurrent visits don't share a live browser page/session with each
      other; they only share the crawler's underlying browser *process* -
      relying on `crawl4ai`'s own multi-session support for that isolation.
    - Everything else - the component/interaction frontier within one page
      visit, the stale-selector resync, route-shape bounding - is per-page,
      single-page-at-a-time logic already, so concurrency at the *page*
      level doesn't change any of it.
    """

    def __init__(
        self,
        crawler: Crawl4AICrawler,
        tracker: Optional[InteractionTracker] = None,
        element_budget: int = 200,
        fill_value_fn: Callable[[Dict[str, Any], str], Awaitable[str]] = default_placeholder_fill_value,
        max_pages: Optional[int] = None,
        sink: Optional[GraphStoreSink] = None,
        max_passes_per_page: int = 10,
        max_visits_per_route_shape: int = 1,
        page_concurrency: int = 1,
        state_transition_overlap_threshold: float = 0.5,
        base_url: Optional[str] = None,
        allow_subdomains: bool = False,
    ) -> None:
        self.crawler = crawler
        self.page_concurrency = max(1, page_concurrency)
        self.element_budget = element_budget
        # Scope boundary for the URL frontier (see `_enqueue`) -
        # `is_in_scope()` (src/utils/urls.py) compares hosts only. `None`
        # (default) means "use crawl_site()'s own start_url" - set here,
        # not required at construction time, the moment `crawl_site()` runs
        # (see its docstring): the overwhelmingly common case is "the crawl
        # never leaves the site it started on," which needs no separate
        # param at all. An explicit `base_url` is only for a caller that
        # wants a *different* scope boundary than where the crawl happens to
        # start (e.g. starting a few pages deep but still scoping to the
        # site root) - not needed for ordinary use.
        self.base_url = base_url
        self.allow_subdomains = allow_subdomains
        # Below this fraction of `known_components` surviving a same-URL DOM
        # change, `_visit_page` treats it as an in-page *state transition*
        # (a new graph node, per `_state_transition_key`) rather than an
        # ordinary reveal (see `_component_overlap_ratio`'s docstring for
        # the empanad.app case this exists for). 0.5 is a deliberately
        # generous default - a real reveal (a dropdown opening) barely
        # touches the ratio at all (everything survives, plus a few new
        # items), so this only fires on a genuine near-total replace; not
        # meant to be precisely tuned per-site.
        self.state_transition_overlap_threshold = state_transition_overlap_threshold
        self.fill_value_fn = fill_value_fn
        self.max_pages = max_pages
        # Backstop against a site that mints a fresh, per-visit-token URL
        # (e.g. `/o/<random-hash>`) on essentially every top-level visit -
        # confirmed live on empanad.app: each token is a distinct clean_url()
        # identity, so an unbounded frontier would treat every new token as a
        # brand-new page forever and never converge. `route_shape()`
        # collapses same-shaped URLs (real identity/navigation untouched -
        # see its docstring) so this can bound "how many instances of this
        # kind of page" get a full visit, independent of `max_pages` (which
        # bounds total pages regardless of shape and has to stay generous for
        # a normal multi-page site). Default 1: an ordinary site has no
        # repeated route shapes at all, so this never fires; raise it to
        # sample more than one instance of a session-token route on purpose.
        self.max_visits_per_route_shape = max_visits_per_route_shape
        # Backstop against a pathological page whose interactions keep
        # revealing genuinely new content faster than element_budget can
        # keep up with (an infinite-scroll/live-chat-style page) - without
        # this, a budget-exhausted page's internal round loop (see
        # _visit_page) could keep interacting with newly-revealed content
        # forever within one continuous session. Same "backstop against a
        # pathological case, not a normal-case limiter" philosophy as
        # element_budget itself - an ordinary page with more components than
        # one round's budget converges in a handful of rounds, well under
        # this default. Together, element_budget * max_passes_per_page is
        # the real total-interactions-per-page-visit ceiling.
        self.max_passes_per_page = max_passes_per_page
        # Phase 3: live GraphStore writes as the crawl happens. `None` keeps
        # Phase 2's behavior (no persistence) - see
        # src/crawlers/graph_sink.py for what each call actually writes and
        # why it's not folded into `tracker` itself.
        self.sink = sink
        # A caller that wires a `sink` almost always wants the matching
        # GraphStore-backed tracker too (same graph_store/site) - defaulted
        # here so a caller doesn't have to construct
        # GraphStoreInteractionTracker by hand every time. An explicit
        # `tracker` always wins (e.g. tests that want a sink's writes
        # recorded but an isolated in-memory tracker for the consult check).
        if tracker is not None:
            self.tracker = tracker
        elif sink is not None:
            self.tracker = GraphStoreInteractionTracker(sink.graph_store, sink.site)
        else:
            self.tracker = InMemoryInteractionTracker()

        # asyncio.Queue, not a plain deque: `crawl_site`'s worker(s) need to
        # `await` for a new item rather than busy-poll, and `.join()` is what
        # lets `crawl_site` know every enqueued item (including ones enqueued
        # *during* another item's processing) has been fully handled, with no
        # separate "is anything still in flight" bookkeeping of its own - see
        # `crawl_site`'s docstring.
        self._url_frontier: "asyncio.Queue[str]" = asyncio.Queue()
        self._queued: Set[str] = set()  # clean_url keys already enqueued or visited, dedup guard
        # clean_url keys a worker is *currently* mid-visit on - a second,
        # narrower guard than `_queued` above, needed specifically because
        # the interrupted-navigation follow-up requeue (see `_worker`)
        # deliberately bypasses `_enqueue`'s `_queued` dedup (it has to: the
        # page it's resuming is, by definition, already in `_queued`). That
        # bypass has no way to know whether some *other*, unrelated page
        # redirected to the exact same destination and already requeued it
        # too - confirmed live on a real crawl (mapadeprofesionales.com,
        # page_concurrency=10): many distinct pages' own "log in" links all
        # redirect to the identical `/login` URL, each interrupted pass
        # independently calls `put_nowait()` for it, and two idle workers
        # ended up running `_visit_page()` for the identical clean_url/
        # session_id at the same time - a real race on the same live crawl4ai
        # browser session (crawl4ai keys its own session cache by this exact
        # string), not just a debug-log cosmetic issue: the *visible* symptom
        # was the debug_log page-markdown snapshot being overwritten
        # mid-flight by whichever worker's write landed second, silently
        # losing the other's. See `_worker` for how this set is
        # maintained/consulted.
        self._in_flight: Set[str] = set()
        self._route_shape_visits: Dict[str, int] = {}  # route_shape() key -> completed-visit count
        self.page_results: List[PageVisitResult] = []
        self.errors: List[ComponentInteraction] = []
        self._pages_visited = 0
        # page_key -> set of _component_identity() tuples already *proven*
        # to navigate away from that page (either cleanly, via the success
        # branch, or detected after an interaction failure - see
        # `_check_for_silent_navigation`). A component's exact `path` churns
        # across separate `discover_page()` reloads on sites where a
        # persistent, site-wide element (a main-nav link, present on every
        # page) gets a framework-assigned id/selector that regenerates on
        # every render - confirmed live on austral.edu.ar: a nav-menu link
        # to a large, slow-to-settle page looked "never tried" on every
        # fresh resume (its path was different every time), so the same
        # navigating click got re-attempted forever, each attempt paying the
        # same failure. `path`-keyed `tracker.is_interacted` alone can never
        # catch this (it's a *different* key each reload, by construction);
        # content identity is stable across the reload precisely because
        # it's independent of any assigned id. Once a component's identity
        # is known to navigate away, `_visit_page` never offers it again for
        # that page_key, regardless of what path it shows up under next.
        self._navigation_trigger_identities: Dict[str, Set[tuple]] = {}
        # page_key -> set of _component_identity() tuples ever successfully
        # or unsuccessfully *interacted with* on that page_key, regardless of
        # path - the same path-churn problem as `_navigation_trigger_identities`
        # above, but for the *ordinary same-page reveal* path instead of the
        # navigation path (a case that set doesn't cover, since nothing here
        # ever navigates at all). Confirmed live on austral.edu.ar: an
        # interactive book-viewer widget (libro_UA30) kept the *exact* same
        # book page open (navigated: False, success: True, ~20-100 components
        # each time) for 155+ separate interactions in one run - a same-page
        # widget (a thumbnail strip/page-turn control) re-renders its DOM
        # under fresh ids on every interaction, so path-based "already
        # interacted" never recognizes the reappearing control as the one
        # just clicked, and the "append newly-revealed components" step (see
        # below) kept treating each fresh render as genuinely new work.
        #
        # Deliberate tradeoff, and worth stating plainly: unlike
        # `_navigation_trigger_identities` (narrowly scoped to a *proven*
        # one-way-door fact), this is a broader rule - two components that
        # happen to share the exact same (tag, role, name, form, text) but
        # are otherwise legitimately distinct (e.g. two "Leer más" cards
        # linking to different articles, both generically labelled) would
        # also collapse under this check, and the second would never be
        # offered. Accepted because the alternative - the crawl never
        # terminating on a churning widget - is unambiguously worse than an
        # occasional missed near-duplicate-looking component; this mirrors
        # the same "decline redundant work over risk overriding a real
        # choice" calculus wiki/graph-based-crawl-tracking.md already
        # documents, applied to a session-local heuristic instead of a
        # cross-run one.
        self._interacted_identities: Dict[str, Set[tuple]] = {}

    def _enqueue(self, url: str) -> None:
        key = clean_url(url)
        if key in self._queued or self.tracker.is_visited(key):
            return
        # Scope gate - the single choke point every discovered URL passes
        # through (a plain link, a follow-up-pass requeue, or a real
        # navigation's destination all call this), so this one check covers
        # every way the crawl could otherwise wander off-site: a link to an
        # external domain, or a click/redirect that lands there (see
        # `_visit_page`'s physical-navigation branch, which calls this with
        # `new_state.url` - an out-of-scope destination there is still
        # correctly recorded as a navigation edge, just never itself
        # visited/crawled further). `self.base_url` is set by `crawl_site()`
        # before its own first `_enqueue()` call if not given explicitly.
        if self.base_url and not is_in_scope(url, self.base_url, self.allow_subdomains):
            print(f"Out of scope (different site than {self.base_url!r}): {url}, skipping.")
            return
        shape = route_shape(url)
        visits = self._route_shape_visits.get(shape, 0)
        if visits >= self.max_visits_per_route_shape:
            print(
                f"Route shape {shape!r} already sampled {visits}x, skipping {url} "
                "to avoid unbounded session-token growth."
            )
            return
        self._queued.add(key)
        self._url_frontier.put_nowait(url)

    def _enqueue_links(self, links: List[Dict[str, str]]) -> None:
        """Queue every http(s) href onto the URL frontier - shared by both
        the initial-discovery call site and every same-page-reveal call site
        in `_visit_page` (see Phase 0's ghost-node fix), so a link that only
        exists inside a revealed dropdown/menu gets queued exactly like one
        present on initial load. Safe to call repeatedly for the same links -
        `_enqueue`'s own dedup guard makes this idempotent.
        """
        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - nothing to navigate to
            if href:
                self._enqueue(href)

    async def crawl_site(self, start_url: str) -> List[PageVisitResult]:
        """Crawl every page reachable from `start_url`, `self.page_concurrency`
        pages at a time.

        Runs that many `_worker()` tasks pulling from the shared
        `asyncio.Queue` frontier, then waits on `_url_frontier.join()` -
        which only returns once every enqueued item (including ones enqueued
        *while* another item is still being processed, e.g. links discovered
        on a page a worker is mid-visit on) has had a matching `task_done()`
        call. That's what makes this safe with concurrency > 1 without any
        extra "is anyone still about to enqueue more work" bookkeeping: a
        plain `while queue: ...` loop (Phase 2's original shape, still
        exactly what runs when `page_concurrency=1`, one worker, one item at
        a time) can't tell "frontier is momentarily empty because we're done"
        apart from "frontier is momentarily empty because another worker is
        about to add more" - `Queue.join()`'s unfinished-task count is
        exactly the fact needed to disambiguate the two.
        """
        if self.base_url is None:
            self.base_url = start_url
        self._enqueue(start_url)
        workers = [asyncio.create_task(self._worker()) for _ in range(self.page_concurrency)]
        await self._url_frontier.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        return self.page_results

    async def _worker(self) -> None:
        """One concurrent visitor - pulls a URL, visits it, requeues or
        marks it visited exactly like the old single-loop body did (see the
        removed `crawl_site` loop this was extracted from). Runs forever
        until cancelled by `crawl_site` right after `_url_frontier.join()`
        returns, at which point every worker is guaranteed to be idly
        blocked on `_url_frontier.get()` (never mid-visit) since `join()`
        only completes once the queue is fully drained.
        """
        while True:
            url = await self._url_frontier.get()
            try:
                if self.max_pages is not None and self._pages_visited >= self.max_pages:
                    # Cap reached - drain the rest of the frontier without
                    # visiting so `.join()` can still complete. A *soft*
                    # bound once page_concurrency > 1 (see class docstring):
                    # concurrent workers can each pass this check before
                    # either increments the counter below.
                    continue
                key = clean_url(url)
                if self.tracker.is_visited(key):
                    continue
                if key in self._in_flight:
                    # Another worker is already actively (re-)visiting this
                    # exact clean_url - a duplicate dequeue, not new work
                    # (see `_in_flight`'s docstring for how this happens even
                    # though `_enqueue`'s own dedup guard exists: two
                    # *different* pages independently redirecting to the same
                    # destination, each requeuing it via the bypass path).
                    # Drop it rather than run a second concurrent
                    # `_visit_page()` for the identical session - the
                    # in-flight worker already owns finishing this page,
                    # including its own follow-up requeue if it gets
                    # interrupted again; dropping this duplicate loses no
                    # coverage, only the redundant/racy second attempt.
                    continue
                self._in_flight.add(key)
                try:
                    result = await self._visit_page(url)
                finally:
                    self._in_flight.discard(key)
                self.page_results.append(result)
                self._pages_visited += 1
                if result.interrupted_by_navigation:
                    # Pass was cut short mid-frontier by a real navigation -
                    # this page is not yet fully explored. Re-queue
                    # `result.resolved_url` directly (bypass `_enqueue`'s
                    # dedup guard, which would otherwise refuse a URL already
                    # in `_queued`) rather than marking it visited. This is
                    # the *only* case that needs a fresh discover_page() call:
                    # the session's live page has physically moved to a
                    # different URL, so there's no "same session" left to
                    # resume. Budget exhaustion (see PageVisitResult.
                    # budget_exhausted_with_frontier_remaining) is handled
                    # entirely inside _visit_page's own internal round loop
                    # instead, deliberately *without* ever re-navigating - a
                    # fresh navigation resets any same-page DOM state a reveal
                    # depends on (confirmed empirically: re-navigating after a
                    # budget-exhausted pass reset a reveal-chain's trigger back
                    # to its pristine unclicked state, but the tracker still
                    # correctly remembered it as already-interacted from the
                    # first pass and skipped it - permanently stranding
                    # everything downstream of that trigger). A page whose
                    # frontier still isn't drained even after
                    # max_passes_per_page internal rounds simply stays Pending
                    # (see _visit_page) rather than being requeued here.
                    #
                    # `resolved_url`, not the original `url` this worker
                    # popped: see PageVisitResult.interrupted_by_navigation's
                    # docstring for the real bug this fixes on a redirecting
                    # entry point (re-requesting the original literal string
                    # re-triggers a *fresh* redirect instead of returning to
                    # this in-progress page).
                    self._url_frontier.put_nowait(result.resolved_url)
                else:
                    self.tracker.mark_visited(key)
                    shape = route_shape(url)
                    self._route_shape_visits[shape] = self._route_shape_visits.get(shape, 0) + 1
            finally:
                self._url_frontier.task_done()

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
        """Resync current DOM state after an "element not found" failure and
        reconcile the remaining, not-yet-attempted frontier against it - see
        `_visit_page`'s except-block for when this runs and
        `_remap_stale_frontier`'s docstring for the reconciliation itself.

        Mutates `frontier` in place (slice-replaces `frontier[idx:]` with the
        reconciled remainder, same length or shorter) and adds every
        surviving item's (possibly new, post-remap) path to
        `seen_paths_this_pass` - without this, a remapped item's new path
        isn't yet known to the pass's own "is this genuinely new" dedup
        check, so the very next successful reveal's append-new-components
        step (see below, in `_visit_page`) would see that same path as
        unseen and queue a duplicate entry for a component already sitting
        in `frontier`. Returns the fresh component snapshot to become the
        pass's new `known_components` baseline, or `None` if the resync call
        itself failed (network/crawl4ai error) - frontier is left untouched
        in that case, same as any other best-effort recovery that couldn't
        get fresh data to act on.
        """
        try:
            fresh_state = await self.crawler.resync(url, session_id)
        except Exception as resync_exc:
            print(f"Warning: stale-selector resync failed for {page_key!r}: {resync_exc}")
            return None

        frontier[idx:], dropped = _remap_stale_frontier(frontier[idx:], fresh_state.components)
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
        """After an interaction failure that wasn't cleanly identified as
        either a stale-selector remount (`_is_element_not_found`) or a
        successful navigation (the success branch's own `new_literal !=
        page_literal` check), check whether the live browser session
        actually moved anyway.

        Confirmed live on austral.edu.ar: a real `<a href>` click can
        physically navigate the browser, but if the destination page is slow
        enough to settle that reading back this module's own success marker
        times out first, `_interact()` raises a plain failure with no
        `resulting_url` at all - from `_visit_page`'s point of view this
        looks identical to an ordinary broken selector, so the loop kept
        attempting every remaining frontier item against a page the session
        had already left, each one *also* doomed the same way, for as many
        components as the original page had - confirmed live: 90+ minutes,
        one single `_visit_page()` call that never returned.

        Uses `resync()` - the same no-op-`js_code` re-discovery
        `_recover_stale_frontier` already uses - purely as a way to read the
        live session's *current* URL; best-effort, since the destination
        page might still be slow enough that even this call fails, in which
        case the caller falls back to its pre-existing behavior (this is a
        strict improvement over that fallback, never worse).

        Returns the live session's current URL if it differs from
        `page_literal` (a real, silently-missed navigation), or `None` if
        the session is confirmed still on the same page, or if the check
        itself couldn't complete.
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
        failed: "ComponentInteraction",
        result: "PageVisitResult",
    ) -> bool:
        """Called from `_visit_page`'s except-block for a failure that isn't
        the stale-remount case - see `_check_for_silent_navigation`'s
        docstring for the real symptom this fixes. Performs the check and,
        if it confirms a silent navigation, all the same bookkeeping the
        success-branch's navigation case does (enqueue the destination, mark
        `interrupted_by_navigation`, remember the content identity, record
        the edge) - kept as its own method purely to keep `_visit_page`
        itself from growing an even deeper nested branch.

        Returns whether `_visit_page`'s interaction loop should stop
        (`True`) - mirroring the success branch's own `break`.
        """
        silently_navigated_to = await self._check_for_silent_navigation(url, session_id, page_literal)
        if silently_navigated_to is None:
            return False
        self._enqueue(silently_navigated_to)
        result.interrupted_by_navigation = True
        self._navigation_trigger_identities.setdefault(page_key, set()).add(_component_identity(component))
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
        """Record and switch this pass onto an in-page SPA state transition
        detected by `_visit_page`'s main loop (`_component_overlap_ratio`
        below `state_transition_overlap_threshold`) - see that call site's
        comment for what triggers this and why. Pure bookkeeping, no crawler
        I/O (the interaction that produced `new_state` already happened) -
        kept as a plain method, not `async`, for exactly that reason.

        Returns `(new_page_key, frontier, seen_paths_this_pass)` - the three
        values the caller's loop locals must be replaced with to continue
        acting against the new node.
        """
        new_page_key = _state_transition_key(page_key, new_state.components)
        result.state_transitions.append(new_page_key)
        if self.sink:
            self.sink.record_navigation_edge(page_key, new_page_key, path, action)
            # The old node is only "Finished" if this transition happened to
            # be its last remaining frontier item - same honesty rule the
            # end-of-method check in `_visit_page` applies to whatever page
            # finishes there. There is no way to resume a partially-drained
            # old node later: a fresh navigation to this same physical URL
            # reloads the SPA's *initial* screen, not this mid-flow one - so
            # an incomplete old node is left exactly as-is (Pending), never
            # marked Finished just because the pass moved on.
            if idx >= frontier_len:
                self.sink.record_page_finished(page_key, len(known_components))
            self.sink.record_page_arrival(
                new_page_key, description=new_state.description, title=new_state.title
            )
            self.sink.record_inventory(new_page_key, new_state.components, new_state.links)
            self.sink.record_text_content(new_page_key, new_state.text_content)
        self._enqueue_links(new_state.links)

        # Rebuilt exactly like the top of _visit_page builds `frontier`/
        # `seen_paths_this_pass` for the first node, just keyed to
        # `new_page_key`. The old node's remaining frontier items (if any)
        # belonged to a screen that's gone - that low-overlap fact is what
        # triggered this branch in the first place - so abandoning them here
        # is correct, not a loss: attempting them would raise "element not
        # found" the moment the pass reached them anyway.
        new_page_nav_triggers = self._navigation_trigger_identities.get(new_page_key, set())
        new_page_interacted_identities = self._interacted_identities.get(new_page_key, set())
        frontier = [
            c for c in new_state.components
            if c.get("visible")
            and not self.tracker.is_interacted(new_page_key, c.get("path"))
            and _component_identity(c) not in new_page_nav_triggers
            and _component_identity(c) not in new_page_interacted_identities
        ]
        seen_paths_this_pass = {c.get("path") for c in frontier}
        return new_page_key, frontier, seen_paths_this_pass

    async def _visit_page(self, url: str) -> PageVisitResult:
        """Visit `url` and mechanically interact with its frontier.

        Stops the interaction pass immediately - does not continue to the
        next frontier item - the moment an interaction's *literal* resulting
        URL differs from this page's own literal URL. This is not optional:
        once a click/fill navigates the session's live page away from `url`
        (e.g. a nav link that's also a discovered component, or any onclick-
        driven `location` change), the session's page object *is* the new
        page - every subsequent `click()`/`fill()` call in this pass would be
        evaluating a selector built for the page that's no longer there,
        which fails outright (confirmed empirically: crawl4ai/Playwright
        raises "Execution context was destroyed, most likely because of a
        navigation") rather than harmlessly no-opping. See
        `PageVisitResult.interrupted_by_navigation` for how the caller
        recovers the rest of this page's frontier in a follow-up pass.

        Deliberately two separate identities are tracked through this
        method, never conflated (per wiki/graph-based-crawl-tracking.md's
        node-identity update): `page_literal` (`clean_url()`) is what the
        *physical browser session* actually did - the only thing safe to
        compare against for the navigation-interruption check above, since
        two different session-token instances of "the same" page
        (`/o/<hash-a>` -> `/o/<hash-b>`) are still a real navigation the live
        page object underwent, selectors and all. `page_key`
        (`route_shape()`) is the *canonical* identity used for every
        GraphStore/tracker write - confirmed live on empanad.app: without
        this, a "start a new order" flow that lands on a fresh `/o/<hash>`
        every time produced one separate, near-duplicate page node per visit
        in the final PRD/component tree for what a human looking at the site
        immediately recognizes as one screen. Collapsing storage identity
        through `route_shape()` also means a component already interacted
        with on one hash instance is correctly recognized as already-covered
        on the next (`tracker.is_interacted(page_key, path)`), including
        across separate runs against a persisted GraphStore.
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

        # Most recently known full component snapshot for this pass - starts
        # as the initial discovery, updated after every same-page reveal (see
        # below) so a later reveal's find_revealed_options diff compares
        # against the immediately preceding snapshot, not the page's original
        # load state (otherwise a cascading reveal - A reveals B, an
        # interaction inside B reveals C - would spuriously report B's own
        # already-revealed content as "new" again when C appears).
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
            # Content-identity exclusions, on top of the path-based one above -
            # see `_navigation_trigger_identities`'s and
            # `_interacted_identities`'s docstrings for why a freshly-reloaded
            # page's own churned selectors can't be caught by the path check
            # alone.
            and _component_identity(c) not in known_nav_triggers
            and _component_identity(c) not in already_interacted_identities
        ]
        seen_paths_this_pass: Set[str] = {c["path"] for c in frontier}
        idx = 0
        interactions_done = 0
        # The real per-visit ceiling: element_budget is deliberately not the
        # hard stop here - a page whose components exceed one budget's worth
        # keeps going, within this same continuous session (no re-
        # navigation - see crawl_site's docstring on why that would reset
        # same-page reveal state), for up to max_passes_per_page "rounds"
        # worth of budget before giving up.
        max_total_interactions = self.element_budget * self.max_passes_per_page

        # Guards against resync-storming: only the *first* "element not
        # found" failure since the last successful interaction in this pass
        # triggers a resync (see the except block below) - if the whole rest
        # of the frontier turns out to be genuinely gone, one resync already
        # told us that; repeating it before any progress is made again would
        # just burn more wait_seconds for the same answer.
        stale_resynced_since_success = False
        # A SEPARATE guard for the silent-navigation check below - kept
        # independent of `stale_resynced_since_success` on purpose. These
        # answer two different questions ("is the rest of my frontier stale"
        # vs. "did THIS specific failing click silently navigate away") and
        # a pass can hit both kinds of failure for different, unrelated
        # components. Confirmed live on austral.edu.ar: a shared flag meant
        # an early "element not found" elsewhere in the same pass silently
        # starved the silent-navigation check for a *later*, different
        # failing component - its content identity never got learned (see
        # `_navigation_trigger_identities`), so every future resume kept
        # re-discovering and re-failing on it, indefinitely, even though the
        # very same component had already been proven, once, to navigate
        # away. Two independent guards is what actually makes both
        # recoveries available within one pass, exactly as each was
        # designed to be used on its own.
        silent_navigation_checked_since_success = False

        while idx < len(frontier) and interactions_done < max_total_interactions:
            component = frontier[idx]
            idx += 1
            path = component["path"]
            if self.tracker.is_interacted(page_key, path):
                continue  # revealed again by an earlier interaction this pass, already handled

            interactions_done += 1
            fillable = _is_fillable(component)

            try:
                if fillable:
                    value = await self.fill_value_fn(component, state.description)
                    new_state = await self.crawler.fill(url, session_id, path, value)
                    interaction = ComponentInteraction(page_key, path, "fill", value=value)
                else:
                    new_state = await self.crawler.click(url, session_id, path)
                    interaction = ComponentInteraction(page_key, path, "click")
            except Exception as exc:
                # Real action failure - per wiki/browser-automation-pitfalls.md,
                # this must be recorded distinctly, never treated as a silent
                # no-op. Logged and the loop continues to the next element -
                # one bad selector on one page must not abort the whole crawl.
                failed = ComponentInteraction(page_key, path, "fill" if fillable else "click", error=str(exc))
                self.errors.append(failed)
                result.interactions.append(failed)
                self.tracker.mark_interacted(page_key, path)  # don't retry a proven-broken target forever
                self._interacted_identities.setdefault(page_key, set()).add(_component_identity(component))
                if self.sink:
                    self.sink.record_interaction(page_key, path, failed.action, value="", resulting_url="")

                if _is_element_not_found(exc) and not stale_resynced_since_success:
                    # Confirmed live on empanad.app: an earlier interaction in
                    # this same pass can remount a component-library subtree
                    # (Radix UI reassigning useId()-based ids), silently
                    # invalidating every later frontier item built from the
                    # pre-remount snapshot - each would otherwise fail
                    # "element not found" in turn, one wait_seconds round trip
                    # apiece, without ever actually reaching the real,
                    # still-there components. Resync once and reconcile the
                    # rest of this pass's frontier against current DOM state -
                    # see _recover_stale_frontier's docstring.
                    stale_resynced_since_success = True
                    fresh_components = await self._recover_stale_frontier(
                        url, session_id, page_key, frontier, idx, result, seen_paths_this_pass
                    )
                    if fresh_components is not None:
                        known_components = fresh_components
                    continue

                if not silent_navigation_checked_since_success:
                    # Not an "element not found" (the stale-remount case
                    # above) - this failure could instead mean the click DID
                    # physically navigate the session away, but timed out
                    # before ever reporting that cleanly. Check once per
                    # failure streak, its OWN guard (independent of
                    # `stale_resynced_since_success` - see this variable's
                    # docstring for why) - this is the fix, not a retry-count
                    # cap: see `_handle_possible_silent_navigation`'s docstring.
                    silent_navigation_checked_since_success = True
                    if await self._handle_possible_silent_navigation(
                        url, session_id, page_key, page_literal, component, path, failed, result
                    ):
                        break
                continue

            stale_resynced_since_success = False
            silent_navigation_checked_since_success = False
            self.tracker.mark_interacted(page_key, path)
            self._interacted_identities.setdefault(page_key, set()).add(_component_identity(component))
            new_literal = clean_url(new_state.url)
            new_key = route_shape(new_state.url)
            interaction.resulting_url = new_literal
            result.interactions.append(interaction)
            if self.sink:
                self.sink.record_interaction(page_key, path, interaction.action, interaction.value, new_literal)
                if new_state.network_requests:
                    self.sink.record_component_network(page_key, path, new_state.network_requests)

            if new_literal != page_literal:
                # Real *physical* navigation - the live browser session moved
                # to a different literal URL, even if it canonicalizes to the
                # same route_shape (e.g. a "start a new order" flow landing on
                # a fresh /o/<hash> every time - the selectors this pass was
                # built for are still gone, so this must still stop the pass,
                # regardless of what the storage layer considers "the same
                # page" - see _visit_page's docstring). Queue it, don't follow
                # inline (avoids a depth-first blowup; the URL frontier picks
                # it up in its own turn, same as any other discovered link,
                # still subject to max_visits_per_route_shape) - AND stop this
                # page's pass right here: the session's page has physically
                # left `page_literal`, so no further frontier item from this
                # pass can be safely acted on.
                self._enqueue(new_state.url)
                result.interrupted_by_navigation = True
                # Remember this component's *content* identity, not just its
                # path, as a proven one-way door out of this page_key - see
                # `_navigation_trigger_identities`'s docstring. A persistent,
                # site-wide element (a main-nav link) always leads to the
                # same place regardless of which page you click it from or
                # what selector it happens to render with this time, so this
                # is safe to remember permanently for this page_key, not just
                # for this one pass.
                self._navigation_trigger_identities.setdefault(page_key, set()).add(
                    _component_identity(component)
                )
                if self.sink:
                    # Canonical-to-canonical edge - if new_key == page_key
                    # (a same-route_shape "restart", per the docstring above)
                    # this is a legitimate self-loop, not a bug: it honestly
                    # records "this action leads back to the same logical
                    # page" instead of fabricating a distinct destination node.
                    self.sink.record_navigation_edge(page_key, new_key, path, interaction.action)
                break
            elif _component_overlap_ratio(known_components, new_state.components) < self.state_transition_overlap_threshold:
                # In-page *state transition*, not a mere reveal - confirmed
                # live on empanad.app's "start order" button: the physical
                # URL never changes (navigated: False throughout - see
                # debug_logs/empanad.app_.../debug.md) but the DOM is almost
                # entirely replaced (3 -> 26 -> 0 -> 11 components across one
                # session). Below `state_transition_overlap_threshold`
                # component-identity overlap between the immediately
                # preceding snapshot and this one, treat it like a real
                # navigation to a *new* graph node instead of merging into
                # this one - a third identity question beyond page_literal/
                # page_key (see this method's docstring): "is this still the
                # same *screen*," answered by DOM-overlap since the URL gives
                # no signal at all for a client-routed SPA. See
                # `_transition_to_new_state` for the actual bookkeeping.
                page_key, frontier, seen_paths_this_pass = self._transition_to_new_state(
                    page_key, new_state, path, interaction.action, idx, len(frontier), known_components, result
                )
                known_components = new_state.components
                idx = 0
            else:
                # Same-URL DOM change - a real, equally-authoritative
                # discovery snapshot in its own right, not just a source of
                # "new" frontier candidates. Re-inventory it exactly like the
                # page's initial snapshot (ghost-node fix - see the plan's
                # "Phase 0" section): without this, a component that only
                # exists because this interaction revealed it (the canonical
                # case: opening a combobox's option popover) never gets its
                # real tag/text/role/component_type persisted - it would only
                # ever reach GraphStore through record_component_interaction's
                # auto-create fallback, which creates a node with every
                # descriptive field blank.
                if self.sink:
                    self.sink.record_inventory(page_key, new_state.components, new_state.links)
                self._enqueue_links(new_state.links)

                # Dropdown/combobox variants: any role="option"-family
                # component present now but not in the immediately preceding
                # snapshot is what this interaction just revealed - attribute
                # it back to the trigger (`path`, the component just acted
                # on), the same way group_steppers/group_choice_sets already
                # attach structured facts to a component's `options` field.
                revealed = find_revealed_options(known_components, new_state.components)
                if self.sink and revealed:
                    self.sink.record_revealed_options(page_key, path, revealed)

                # Append genuinely-new, visible, not-yet-interacted components
                # to *this pass's* frontier, still bounded by the same
                # element_budget counter. `page_key` here, not a stale outer
                # value - see `_transition_to_new_state`'s docstring: a state
                # transition earlier in this same pass can have already
                # swapped it.
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
                    if _component_identity(candidate) in current_nav_triggers:
                        continue
                    if _component_identity(candidate) in current_interacted_identities:
                        # Confirmed live on austral.edu.ar (libro_UA30 book
                        # viewer): a same-page widget re-renders under a
                        # fresh path on every interaction, so the path-based
                        # checks above never recognize it as the one just
                        # clicked - see `_interacted_identities`'s docstring
                        # for the tradeoff this accepts.
                        continue
                    seen_paths_this_pass.add(cpath)
                    frontier.append(candidate)

                # This reveal's outcome becomes the baseline the *next*
                # reveal's find_revealed_options diff compares against (see
                # this variable's introduction above `result = ...`).
                known_components = new_state.components

        # Only a true budget exhaustion, not a navigation-interrupted pass
        # (which also leaves `idx < len(frontier)`, but for an unrelated
        # reason - see interrupted_by_navigation).
        result.budget_exhausted_with_frontier_remaining = (
            not result.interrupted_by_navigation and idx < len(frontier)
        )
        if self.sink and not result.interrupted_by_navigation and not result.budget_exhausted_with_frontier_remaining:
            # A pass cut short - by navigation, or by hitting element_budget
            # with real components still un-interacted - leaves the page
            # genuinely incomplete. It must stay Pending for its follow-up
            # pass (see crawl_site's requeue logic and
            # GraphStoreSink.record_page_finished's docstring), not be
            # marked Finished here just because *a* pass happened. Before
            # this fix, a budget-exhausted pass (unlike a navigation-
            # interrupted one) was incorrectly marked Finished on its very
            # first pass, permanently losing whatever didn't fit in that
            # one visit's budget - the same root shape as the Phase 0
            # ghost-node bug, just for "was this page actually fully
            # explored" instead of "does this component have real data."
            # `known_components`, not `state.components` (the *initial*
            # snapshot only) - a page that went through same-page reveals or
            # a state transition finishes with `page_key`/`known_components`
            # both pointing at whatever node this pass actually ended on, and
            # the component count recorded should describe that node, not
            # the first one this visit ever saw.
            self.sink.record_page_finished(page_key, len(known_components))
        return result
