# `spiders/orchestration/page_visitor/outcomes.py`

## module

What bookkeeping follows each of the three ways a successful interaction
can change page state: a real physical navigation, an in-page SPA state
transition, or a same-URL DOM reveal. Split out of `PageVisitor` - the
normal success-path bookkeeping, independent of `recovery.py`'s failure-
path reconciliation.

## InteractionOutcomes

Takes `tracker`/`enqueue_url`/`enqueue_links`/`sink`/the shared
`Frontier`/`is_known_url` as constructor dependencies - `PageVisitor.__init__`
is the composition root that wires these once per instance. `is_known_url`
is `UrlFrontier.is_known` bound through - see
`docs/dev/spiders/orchestration/mechanical_loop/frontier.md#is_known` and
`handle_physical_navigation` below for what it's used for.

## transition_to_new_state

Record and switch this pass onto an in-page SPA state transition detected
by `visit`'s main loop (`component_matching.component_overlap_ratio`
below `state_transition_overlap_threshold`) - see
`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-state-transition-branch`
for what triggers this and why.

Returns `(new_page_key, frontier, seen_paths_this_pass)` - the three
values the caller's loop locals must be replaced with to continue acting
against the new node.

## transition_to_new_state-finished-check

The old node is only "Finished" if this transition happened to be its
last remaining frontier item - same honesty rule
`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-record-page-finished`
applies to whatever page finishes there. There is no way to resume a
partially-drained old node later: a fresh navigation to this same
physical URL reloads the SPA's *initial* screen, not this mid-flow one -
so an incomplete old node is left exactly as-is (Pending), never marked
Finished just because the pass moved on.

## transition_to_new_state-frontier-rebuild

Rebuilt via `Frontier.eligible()`, the same call `visit()` makes for the
first node, just keyed to `new_page_key`. The old node's remaining
frontier items (if any) belonged to a screen that's gone - that low-
overlap fact is what triggered this branch in the first place - so
abandoning them here is correct, not a loss: attempting them would raise
"element not found" the moment the pass reached them anyway.

## handle_physical_navigation

`visit`'s response to an interaction whose *literal* result URL differs
from the page it was interacted on - the live browser session moved to a
different literal URL, even if it canonicalizes to the same route_shape
(e.g. a "start a new order" flow landing on a fresh `/o/<hash>` every
time - the selectors this pass was built for are still gone either way).

Always records the edge and the navigation-trigger identity (below) -
that bookkeeping is true regardless of where the click led. Whether the
*pass* actually has to stop depends on `is_known_url(new_state.url)`:

- **Unknown destination** (the crawl has never queued, visited, or is
  currently mid-visit on it): queues it and returns `True`. `visit`
  breaks and the whole page gets requeued for a separate later pass -
  avoids a depth-first blowup; the URL frontier picks the destination up
  in its own turn, same as any other discovered link, still subject to
  `max_visits_per_route_shape`.
- **Known destination**: does *not* enqueue it (nothing to add - it's
  already accounted for) and returns `False`. `visit` then calls
  `NavigationRecovery.return_to_origin` to hop the browser straight back
  and keep draining this same page's frontier, instead of pausing the
  whole pass for a link that doesn't need one.

Confirmed live on austral.edu.ar: a site-wide nav menu means nearly every
page links to nearly every other page, so nearly every one of the first
few clicks on any page was a known-destination navigation - before this
distinction existed, each one interrupted the pass regardless, and most
pages exhausted `max_requeue_attempts`
(`docs/dev/spiders/orchestration/mechanical_loop/config.md#max_requeue_attempts`)
purely on nav-menu links and were marked Failed before ever reaching their
own content.

## handle_physical_navigation-identity

Remember this component's *content* identity, not just its path, as a
proven one-way door out of this page_key via `Frontier.mark_navigation_trigger`
- see
`docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities`.
A persistent, site-wide element (a main-nav link) always leads to the
same place regardless of which page you click it from or what selector
it happens to render with this time, so this is safe to remember
permanently for this page_key, not just for this one pass.

## handle_physical_navigation-self-loop

Canonical-to-canonical edge - if `new_key == page_key` (a
same-route_shape "restart," per `handle_physical_navigation` above) this
is a legitimate self-loop, not a bug: it honestly records "this action
leads back to the same logical page" instead of fabricating a distinct
destination node.

## handle_same_page_reveal

`visit`'s response to an interaction that changed the DOM without
navigating - a real, equally-authoritative discovery snapshot in its own
right, not just a source of "new" frontier candidates. Re-inventories it
exactly like the page's initial snapshot (ghost-node fix): without this,
a component that only exists because this interaction revealed it (the
canonical case: opening a combobox's option popover) never gets its real
tag/text/role/component_type persisted - it would only ever reach
GraphStore through `record_component_interaction`'s auto-create fallback,
which creates a node with every descriptive field blank.

Mutates `frontier`/`seen_paths_this_pass` in place (appending
genuinely-new candidates) and returns the snapshot that becomes the
baseline for the *next* reveal's `find_revealed_options` diff.

## handle_same_page_reveal-revealed-options

Dropdown/combobox variants: any `role="option"`-family component present
now but not in the immediately preceding snapshot is what this
interaction just revealed - attribute it back to the trigger (`path`,
the component just acted on), the same way `group_steppers`/
`group_choice_sets` already attach structured facts to a component's
`options` field.

## handle_same_page_reveal-append-frontier

Append genuinely-new, visible, not-yet-interacted components to *this
pass's* frontier - no numeric ceiling on how large it can grow (see
`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop`).
`page_key` here, not a stale outer value - see
`transition_to_new_state-frontier-rebuild`: a state transition earlier
in this same pass can have already swapped it.

The skipped-as-churning-widget branch (via `Frontier.is_excluded`):
confirmed live on austral.edu.ar (libro_UA30 book viewer) - a same-page
widget re-renders under a fresh path on every interaction, so the
path-based checks above never recognize it as the one just clicked - see
`docs/dev/spiders/orchestration/page_visitor/frontier.md#_interacted_identities`
for the tradeoff this accepts.
