# `spiders/orchestration/page_visitor/frontier.py`

## module

Which components are eligible for `PageVisitor`'s interaction frontier,
and why some get excluded even though they're still visible and
unvisited. Replaces two near-identical list comprehensions that used to
live inline in `visit()` and (what is now) `outcomes.py`'s
`transition_to_new_state` - a real `core-dry` fix, not just a move.

## Frontier

Owns the per-page navigation-trigger and interacted-identity sets, and
the eligibility rule built from them.

## _navigation_trigger_identities

page_key -> set of `component_identity()` tuples already *proven* to
navigate away from that page (either cleanly, via the success branch, or
detected after an interaction failure - see
`docs/dev/spiders/orchestration/page_visitor/recovery.md#check_for_silent_navigation`).
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
`eligible()` never offers it again for that page_key, regardless of what
path it shows up under next.

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

## is_excluded

Single-component check used by `outcomes.py`'s
`handle_same_page_reveal` when appending one newly-revealed candidate at
a time, rather than rebuilding a whole frontier - same exclusion rule as
`eligible()`, factored out so the two never drift apart.

## eligible

Build a fresh interaction frontier from a page's components: visible, not
already interacted (per the `InteractionTracker` passed in), and not
excluded (per `is_excluded`). Returns the frontier plus the set of paths
it contains, since every caller needs both - `visit()`'s own initial
frontier build and `outcomes.py`'s `transition_to_new_state` rebuild both
call this instead of duplicating the list comprehension.

## mark_navigation_trigger

Remember a component's content identity as a proven one-way door out of
a page_key - see `_navigation_trigger_identities` above. A persistent,
site-wide element (a main-nav link) always leads to the same place
regardless of which page you click it from or what selector it happens
to render with this time, so this is safe to remember permanently for
this page_key, not just for one pass.

## mark_interacted_identity

Details: see `_interacted_identities` above for the tradeoff this records.
