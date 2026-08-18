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

## skip_known_link

The primary, cheaper sibling to `handle_physical_navigation` below - for
the specific case of a real `<a href>` component whose destination
`visit`'s own pre-click check
(`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-static-href-check`)
already resolved and found already-known, *before* any click happened.
Same edge-recording and identity-exclusion as the followed-link case, but
there is no `new_state`/`interaction` to build a `ComponentInteraction`
from - nothing was attempted, so nothing goes into `result.interactions`
either, the same discipline every other silently-skipped component
(excluded/churning-widget) already follows.

## handle_physical_navigation

`visit`'s response to an interaction whose *literal* result URL differs
from the page it was interacted on - the live browser session moved to a
different literal URL, even if it canonicalizes to the same route_shape
(e.g. a "start a new order" flow landing on a fresh `/o/<hash>` every
time - the selectors this pass was built for are still gone either way).

Only reached for a component `skip_known_link` couldn't already handle
statically - a fillable field, a non-anchor clickable (an `onclick`
handler, not a real `href`), or an anchor whose href resolved to
something *not* already known. A real, physical browser navigation
already happened by the time this runs; unlike `skip_known_link`, there's
no way to avoid it after the fact, only to decide what to do about it.

Always records the edge and the navigation-trigger identity (below) -
that bookkeeping is true regardless of where the click led. Enqueues the
destination only if `is_known_url(new_state.url)` says the crawl doesn't
already have a place for it (queued, in flight, or visited already) -
nothing to add otherwise, it's already accounted for.

Purely bookkeeping now - doesn't decide whether the pass stops. `visit`
always follows this with `NavigationRecovery.return_to_origin` to hop the
browser straight back and keep draining this same page's frontier,
known destination or not; `return_to_origin`'s own failure fallback is
what handles a genuinely unrecoverable session, not a decision made here.

**Update - originally only did this for a *known* destination, unknown
ones always stopped the pass**: confirmed live on austral.edu.ar, that
first version fixed the measured problem (a site-wide nav menu meant
nearly every page's first few clicks were known-destination navigations,
each interrupting the pass and exhausting `max_requeue_attempts`
(`docs/dev/spiders/orchestration/mechanical_loop/config.md#max_requeue_attempts`)
purely on nav-menu links before ever reaching a page's own content) but
left the *unknown*-destination case interrupting for no proven technical
reason - it was scoped narrowly to the specific bug being fixed, not
because eager resume-in-place is actually unsafe for new content.
Re-examined this session: `go_back`'s browser-history mechanism doesn't
care what our own Python bookkeeping calls a destination, and the
destination's own content was already being discarded-and-refetched
either way (this method never inventories `new_state` before the
pass moves on - a known destination already has its own inventory from
whenever it was first discovered; an unknown one gets one for free from
its own future `discover_page()` visit, same as before). The only thing
that changed is the *origin* no longer pays for a second full render just
because the destination happened to be new.

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
