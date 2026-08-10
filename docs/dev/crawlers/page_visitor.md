# `src/crawlers/page_visitor.py`

## module

The mechanical crawl loop's single-page interaction state machine - split
out from `mechanical_loop.py`'s `MechanicalCrawler`, which owns the
*site*-level URL frontier/worker orchestration instead. `MechanicalCrawler`
constructs one `PageVisitor` per crawl and hands every dequeued URL to
`visit()`; this module never touches the URL frontier itself, only the
`enqueue_url`/`enqueue_links` callbacks passed in at construction time.

## _max_consecutive_unexplained_failures

Circuit breaker for `visit`'s interaction loop - see
`visit-except-circuit-breaker-trip` below for the exact symptom this
bounds (a session parked on a page that never finishes loading makes the
silent-navigation check itself fail the same way every real interaction
does, so nothing else stops the pass from burning the entire remaining
frontier one interaction-timeout at a time). Deliberately small and
deliberately not the same knob as `element_budget`/`max_passes_per_page`
(those bound normal, working exploration; this bounds a pass that's
already shown it isn't converging).

## PageVisitor

Mechanically interacts with one page's frontier at a time, called once
per URL by `MechanicalCrawler._worker`. Holds the identity-tracking state
that must persist *across* visits within one crawl (`errors`,
`_navigation_trigger_identities`, `_interacted_identities`) - constructed
once per `MechanicalCrawler` and reused for every `visit()` call, not a
per-visit throwaway.

## _navigation_trigger_identities

page_key -> set of `component_identity()` tuples already *proven* to
navigate away from that page (either cleanly, via the success branch, or
detected after an interaction failure - see `_check_for_silent_navigation`).
A component's exact `path` churns across separate `discover_page()`
reloads on sites where a persistent, site-wide element (a main-nav link,
present on every page) gets a framework-assigned id/selector that
regenerates on every render - confirmed live on austral.edu.ar: a
nav-menu link to a large, slow-to-settle page looked "never tried" on
every fresh resume (its path was different every time), so the same
navigating click got re-attempted forever, each attempt paying the same
failure. `path`-keyed `tracker.is_interacted` alone can never catch this
(it's a *different* key each reload, by construction); content identity
is stable across the reload precisely because it's independent of any
assigned id. Once a component's identity is known to navigate away,
`visit` never offers it again for that page_key, regardless of what path
it shows up under next.

## _interacted_identities

page_key -> set of `component_identity()` tuples ever successfully or
unsuccessfully *interacted with* on that page_key, regardless of path -
the same path-churn problem as `_navigation_trigger_identities` above,
but for the *ordinary same-page reveal* path instead of the navigation
path (a case that set doesn't cover, since nothing here ever navigates at
all). Confirmed live on austral.edu.ar: an interactive book-viewer widget
(libro_UA30) kept the *exact* same book page open (navigated: False,
success: True, ~20-100 components each time) for 155+ separate
interactions in one run - a same-page widget (a thumbnail strip/page-turn
control) re-renders its DOM under fresh ids on every interaction, so
path-based "already interacted" never recognizes the reappearing control
as the one just clicked, and the "append newly-revealed components" step
kept treating each fresh render as genuinely new work.

Deliberate tradeoff, and worth stating plainly: unlike
`_navigation_trigger_identities` (narrowly scoped to a *proven*
one-way-door fact), this is a broader rule - two components that happen
to share the exact same (tag, role, name, form, text) but are otherwise
legitimately distinct (e.g. two "Leer más" cards linking to different
articles, both generically labelled) would also collapse under this
check, and the second would never be offered. Accepted because the
alternative - the crawl never terminating on a churning widget - is
unambiguously worse than an occasional missed near-duplicate-looking
component; this mirrors the same "decline redundant work over risk
overriding a real choice" calculus wiki/graph-based-crawl-tracking.md
already documents, applied to a session-local heuristic instead of a
cross-run one.

## _recover_stale_frontier

Resync current DOM state after an "element not found" failure and
reconcile the remaining, not-yet-attempted frontier against it - see
`visit-except-stale-resync` for when this runs and
`docs/dev/crawlers/component_matching.md#remap_stale_frontier` for the
reconciliation itself.

Mutates `frontier` in place (slice-replaces `frontier[idx:]` with the
reconciled remainder, same length or shorter) and adds every surviving
item's (possibly new, post-remap) path to `seen_paths_this_pass` -
without this, a remapped item's new path isn't yet known to the pass's
own "is this genuinely new" dedup check, so the very next successful
reveal's append-new-components step (`_handle_same_page_reveal`) would
see that same path as unseen and queue a duplicate entry for a component
already sitting in `frontier`. Returns the fresh component snapshot to
become the pass's new `known_components` baseline, or `None` if the
resync call itself failed (network/crawl4ai error) - frontier is left
untouched in that case, same as any other best-effort recovery that
couldn't get fresh data to act on.

## _check_for_silent_navigation

After an interaction failure that wasn't cleanly identified as either a
stale-selector remount (`component_matching.is_element_not_found`) or a
successful navigation (the success branch's own `new_literal !=
page_literal` check), check whether the live browser session actually
moved anyway.

Confirmed live on austral.edu.ar: a real `<a href>` click can physically
navigate the browser, but if the destination page is slow enough to
settle that reading back this module's own success marker times out
first, `_interact()` raises a plain failure with no `resulting_url` at
all - from `visit`'s point of view this looks identical to an ordinary
broken selector, so the loop kept attempting every remaining frontier
item against a page the session had already left, each one *also* doomed
the same way, for as many components as the original page had -
confirmed live: 90+ minutes, one single `visit()` call that never
returned.

Uses `resync()` - the same no-op-`js_code` re-discovery
`_recover_stale_frontier` already uses - purely as a way to read the live
session's *current* URL; best-effort, since the destination page might
still be slow enough that even this call fails, in which case the caller
falls back to its pre-existing behavior (this is a strict improvement
over that fallback, never worse).

Returns the live session's current URL if it differs from `page_literal`
(a real, silently-missed navigation), or `None` if the session is
confirmed still on the same page, or if the check itself couldn't
complete.

## _handle_possible_silent_navigation

Called from `visit`'s except-block for a failure that isn't the
stale-remount case - see `_check_for_silent_navigation` above for the
real symptom this fixes. Performs the check and, if it confirms a silent
navigation, all the same bookkeeping the success-branch's navigation case
does (enqueue the destination, mark `interrupted_by_navigation`,
remember the content identity, record the edge) - kept as its own method
purely to keep `visit` itself from growing an even deeper nested branch.

Returns whether `visit`'s interaction loop should stop (`True`) -
mirroring the success branch's own `break`.

## _transition_to_new_state

Record and switch this pass onto an in-page SPA state transition detected
by `visit`'s main loop (`component_matching.component_overlap_ratio`
below `state_transition_overlap_threshold`) - see
`visit-state-transition-branch` for what triggers this and why. Pure
bookkeeping, no crawler I/O (the interaction that produced `new_state`
already happened) - kept as a plain method, not `async`, for exactly that
reason.

Returns `(new_page_key, frontier, seen_paths_this_pass)` - the three
values the caller's loop locals must be replaced with to continue acting
against the new node.

## _transition_to_new_state-finished-check

The old node is only "Finished" if this transition happened to be its
last remaining frontier item - same honesty rule
`visit-record-page-finished` applies to whatever page finishes there.
There is no way to resume a partially-drained old node later: a fresh
navigation to this same physical URL reloads the SPA's *initial* screen,
not this mid-flow one - so an incomplete old node is left exactly as-is
(Pending), never marked Finished just because the pass moved on.

## _transition_to_new_state-frontier-rebuild

Rebuilt exactly like the top of `visit` builds `frontier`/
`seen_paths_this_pass` for the first node, just keyed to `new_page_key`.
The old node's remaining frontier items (if any) belonged to a screen
that's gone - that low-overlap fact is what triggered this branch in the
first place - so abandoning them here is correct, not a loss: attempting
them would raise "element not found" the moment the pass reached them
anyway.

## _handle_physical_navigation

`visit`'s response to an interaction whose *literal* result URL differs
from the page it was interacted on - the live browser session moved to a
different literal URL, even if it canonicalizes to the same route_shape
(e.g. a "start a new order" flow landing on a fresh `/o/<hash>` every
time - the selectors this pass was built for are still gone, so the
caller must still stop the pass, regardless of what the storage layer
considers "the same page"). Queues the destination rather than following
it inline (avoids a depth-first blowup; the URL frontier picks it up in
its own turn, same as any other discovered link, still subject to
`max_visits_per_route_shape`).

## _handle_physical_navigation-identity

Remember this component's *content* identity, not just its path, as a
proven one-way door out of this page_key - see
`_navigation_trigger_identities` above. A persistent, site-wide element
(a main-nav link) always leads to the same place regardless of which
page you click it from or what selector it happens to render with this
time, so this is safe to remember permanently for this page_key, not
just for this one pass.

## _handle_physical_navigation-self-loop

Canonical-to-canonical edge - if `new_key == page_key` (a
same-route_shape "restart," per `_handle_physical_navigation` above) this
is a legitimate self-loop, not a bug: it honestly records "this action
leads back to the same logical page" instead of fabricating a distinct
destination node.

## _handle_same_page_reveal

`visit`'s response to an interaction that changed the DOM without
navigating - a real, equally-authoritative discovery snapshot in its own
right, not just a source of "new" frontier candidates. Re-inventories it
exactly like the page's initial snapshot (ghost-node fix - see the plan's
"Phase 0" section): without this, a component that only exists because
this interaction revealed it (the canonical case: opening a combobox's
option popover) never gets its real tag/text/role/component_type
persisted - it would only ever reach GraphStore through
`record_component_interaction`'s auto-create fallback, which creates a
node with every descriptive field blank.

Mutates `frontier`/`seen_paths_this_pass` in place (appending
genuinely-new candidates) and returns the snapshot that becomes the
baseline for the *next* reveal's `find_revealed_options` diff.

## _handle_same_page_reveal-revealed-options

Dropdown/combobox variants: any `role="option"`-family component present
now but not in the immediately preceding snapshot is what this
interaction just revealed - attribute it back to the trigger (`path`,
the component just acted on), the same way `group_steppers`/
`group_choice_sets` already attach structured facts to a component's
`options` field.

## _handle_same_page_reveal-append-frontier

Append genuinely-new, visible, not-yet-interacted components to *this
pass's* frontier, still bounded by the same `element_budget` counter.
`page_key` here, not a stale outer value - see
`_transition_to_new_state-frontier-rebuild`: a state transition earlier
in this same pass can have already swapped it.

The skipped-as-churning-widget branch: confirmed live on austral.edu.ar
(libro_UA30 book viewer) - a same-page widget re-renders under a fresh
path on every interaction, so the path-based checks above never
recognize it as the one just clicked - see `_interacted_identities` for
the tradeoff this accepts.

## visit

Visit `url` and mechanically interact with its frontier.

Stops the interaction pass immediately - does not continue to the next
frontier item - the moment an interaction's *literal* resulting URL
differs from this page's own literal URL. This is not optional: once a
click/fill navigates the session's live page away from `url` (e.g. a nav
link that's also a discovered component, or any onclick-driven `location`
change), the session's page object *is* the new page - every subsequent
`click()`/`fill()` call in this pass would be evaluating a selector built
for the page that's no longer there, which fails outright (confirmed
empirically: crawl4ai/Playwright raises "Execution context was destroyed,
most likely because of a navigation") rather than harmlessly no-opping.
See `docs/dev/crawlers/visit_result.md#pagevisitresultinterrupted_by_navigation`
for how the caller recovers the rest of this page's frontier in a
follow-up pass.

Deliberately two separate identities are tracked through this method,
never conflated (per wiki/graph-based-crawl-tracking.md's node-identity
update): `page_literal` (`clean_url()`) is what the *physical browser
session* actually did - the only thing safe to compare against for the
navigation-interruption check above, since two different session-token
instances of "the same" page (`/o/<hash-a>` -> `/o/<hash-b>`) are still a
real navigation the live page object underwent, selectors and all.
`page_key` (`route_shape()`) is the *canonical* identity used for every
GraphStore/tracker write - confirmed live on empanad.app: without this, a
"start a new order" flow that lands on a fresh `/o/<hash>` every time
produced one separate, near-duplicate page node per visit in the final
PRD/component tree for what a human looking at the site immediately
recognizes as one screen. Collapsing storage identity through
`route_shape()` also means a component already interacted with on one
hash instance is correctly recognized as already-covered on the next
(`tracker.is_interacted(page_key, path)`), including across separate runs
against a persisted GraphStore.

## visit-known-components

Most recently known full component snapshot for this pass - starts as
the initial discovery, updated after every same-page reveal so a later
reveal's `find_revealed_options` diff compares against the immediately
preceding snapshot, not the page's original load state (otherwise a
cascading reveal - A reveals B, an interaction inside B reveals C - would
spuriously report B's own already-revealed content as "new" again when C
appears).

## visit-content-identity-exclusions

See `_navigation_trigger_identities` and `_interacted_identities` above
for why a freshly-reloaded page's own churned selectors can't be caught
by the path check alone.

## visit-max-total-interactions

The real per-visit ceiling: `element_budget` is deliberately not the hard
stop here - a page whose components exceed one budget's worth keeps
going, within this same continuous session (no re-navigation - see
`docs/dev/crawlers/mechanical_loop.md#crawl_site` on why that would reset
same-page reveal state), for up to `max_passes_per_page` "rounds" worth
of budget before giving up.

## visit-guards

Three independent per-pass guards, each answering a different question:

- `stale_resynced_since_success` - guards against resync-storming: only
  the *first* "element not found" failure since the last successful
  interaction in this pass triggers a resync (see
  `visit-except-stale-resync`) - if the whole rest of the frontier turns
  out to be genuinely gone, one resync already told us that; repeating it
  before any progress is made again would just burn more `wait_seconds`
  for the same answer.
- `silent_navigation_checked_since_success` - a SEPARATE guard for the
  silent-navigation check, kept independent of the one above on purpose.
  These answer two different questions ("is the rest of my frontier
  stale" vs. "did THIS specific failing click silently navigate away")
  and a pass can hit both kinds of failure for different, unrelated
  components. Confirmed live on austral.edu.ar: a shared flag meant an
  early "element not found" elsewhere in the same pass silently starved
  the silent-navigation check for a *later*, different failing component
  - its content identity never got learned (see
  `_navigation_trigger_identities`), so every future resume kept
  re-discovering and re-failing on it, indefinitely, even though the very
  same component had already been proven, once, to navigate away. Two
  independent guards is what actually makes both recoveries available
  within one pass, exactly as each was designed to be used on its own.
- `consecutive_unexplained_failures` - circuit breaker, independent of
  both guards above. Confirmed live on austral.edu.ar: a session that
  lands on a page whose own `domcontentloaded` never fires (a WAF holding
  the response open) makes `_handle_possible_silent_navigation`'s own
  `resync()` call fail the *exact* same way every subsequent real
  interaction does - the ONE check built to catch "did we silently
  navigate away" is exactly the one guaranteed to also come back
  inconclusive here, and since it only runs once per failure streak,
  every remaining frontier item then gets attempted anyway, each
  independently burning a full interaction-timeout before failing the
  same way - confirmed live: 40+ consecutive identical `Timeout 30000ms
  exceeded` failures over 40+ minutes, still climbing, on one single
  page. This counts *consecutive* failures that reach this specific
  branch (not stale-selector remounts, which are a different,
  already-understood recovery) and gives up on the pass - not silently,
  not forever - once continuing clearly isn't converging on anything.

## visit-except-real-failure

Real action failure - per wiki/browser-automation-pitfalls.md, this must
be recorded distinctly, never treated as a silent no-op. Logged and the
loop continues to the next element - one bad selector on one page must
not abort the whole crawl.

## visit-except-stale-resync

Confirmed live on empanad.app: an earlier interaction in this same pass
can remount a component-library subtree (Radix UI reassigning
`useId()`-based ids), silently invalidating every later frontier item
built from the pre-remount snapshot - each would otherwise fail "element
not found" in turn, one `wait_seconds` round trip apiece, without ever
actually reaching the real, still-there components. Resync once and
reconcile the rest of this pass's frontier against current DOM state -
see `_recover_stale_frontier`.

## visit-except-not-element-not-found

Not an "element not found" (the stale-remount case above) - counts
toward the circuit breaker below regardless of whether the
silent-navigation check itself runs this iteration (its own guard only
allows one attempt per streak - see `visit-guards`) or was already
consumed by an earlier, unrelated failure this pass.

## visit-except-silent-nav-check

This failure could instead mean the click DID physically navigate the
session away, but timed out before ever reporting that cleanly. Check
once per failure streak, its OWN guard (independent of
`stale_resynced_since_success` - see `visit-guards` for why) - this is
the fix, not a retry-count cap: see `_handle_possible_silent_navigation`.

## visit-except-circuit-breaker-trip

The silent-navigation check above is itself just another interaction
against this same session - if the session is genuinely dead (parked on
a page that never finishes loading), that check fails the identical way
every real interaction does, so it can never confirm what it exists to
confirm. Give up on this pass rather than burning the rest of the
frontier the same way, one interaction-timeout at a time - not a
confirmed navigation, but the same recovery (requeue this page for a
fresh visit later - see
`docs/dev/crawlers/visit_result.md#pagevisitresultinterrupted_by_navigation`)
is the right honest outcome: this pass isn't converging, and a fresh
session may not be stuck the same way.

## visit-physical-navigation-branch

Real *physical* navigation - the live browser session moved to a
different literal URL, even if it canonicalizes to the same route_shape
(e.g. a "start a new order" flow landing on a fresh `/o/<hash>` every
time - the selectors this pass was built for are still gone, so this
must still stop the pass, regardless of what the storage layer considers
"the same page" - see `visit`'s own doc above). Queue it, don't follow
inline (avoids a depth-first blowup; the URL frontier picks it up in its
own turn, same as any other discovered link, still subject to
`max_visits_per_route_shape`) - AND stop this page's pass right here: the
session's page has physically left `page_literal`, so no further frontier
item from this pass can be safely acted on.

## visit-state-transition-branch

In-page *state transition*, not a mere reveal - confirmed live on
empanad.app's "start order" button: the physical URL never changes
(`navigated: False` throughout - see `debug_logs/empanad.app_.../debug.md`)
but the DOM is almost entirely replaced (3 -> 26 -> 0 -> 11 components
across one session). Below `state_transition_overlap_threshold`
component-identity overlap between the immediately preceding snapshot and
this one, treat it like a real navigation to a *new* graph node instead
of merging into this one - a third identity question beyond
page_literal/page_key (see `visit`'s own doc above): "is this still the
same *screen*," answered by DOM-overlap since the URL gives no signal at
all for a client-routed SPA. See `_transition_to_new_state` for the
actual bookkeeping.

## visit-same-page-branch

Same-URL DOM change - a real, equally-authoritative discovery snapshot in
its own right, not just a source of "new" frontier candidates. Re-
inventoried exactly like the page's initial snapshot (ghost-node fix -
see the plan's "Phase 0" section): without this, a component that only
exists because this interaction revealed it (the canonical case: opening
a combobox's option popover) never gets its real
tag/text/role/component_type persisted - it would only ever reach
GraphStore through `record_component_interaction`'s auto-create fallback,
which creates a node with every descriptive field blank. See
`_handle_same_page_reveal`.

## visit-budget-exhausted

Only a true budget exhaustion, not a navigation-interrupted pass (which
also leaves `idx < len(frontier)`, but for an unrelated reason - see
`docs/dev/crawlers/visit_result.md#pagevisitresultinterrupted_by_navigation`).

## visit-record-page-finished

A pass cut short - by navigation, or by hitting `element_budget` with
real components still un-interacted - leaves the page genuinely
incomplete. It must stay Pending for its follow-up pass (see
`docs/dev/crawlers/mechanical_loop.md#crawl_site`'s requeue logic and
`docs/dev/crawlers/graph_sink.md#record_page_finished`), not be marked
Finished here just because *a* pass happened. Before this fix, a
budget-exhausted pass (unlike a navigation-interrupted one) was
incorrectly marked Finished on its very first pass, permanently losing
whatever didn't fit in that one visit's budget - the same root shape as
the Phase 0 ghost-node bug, just for "was this page actually fully
explored" instead of "does this component have real data."
`known_components`, not `state.components` (the *initial* snapshot
only) - a page that went through same-page reveals or a state transition
finishes with `page_key`/`known_components` both pointing at whatever
node this pass actually ended on, and the component count recorded
should describe that node, not the first one this visit ever saw.
