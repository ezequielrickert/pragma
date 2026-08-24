# `spiders/orchestration/page_visitor/frontier.py`

## module

Which components are eligible for `PageVisitor`'s interaction frontier,
and the per-page canonical-path map every reveal needs. Replaces a list
comprehension that used to live inline in `visit()` and (what is now)
`outcomes.py`'s `transition_to_new_state` - a real `core-dry` fix, not
just a move.

## Frontier

Owns the interaction-eligibility rule and the per-page canonical-path
map - one shared `Frontier` instance for the whole crawl (constructed
once by `PageVisitor.__init__`, itself constructed once by
`MechanicalCrawler`), not one per visit.

**Update - issue #214, content-identity-based skipping dropped:** this
class used to also own a site-wide navigation-trigger set and a per-page
interacted-identity set (`_navigation_trigger_identities`,
`_interacted_identities`, `is_excluded`, `mark_navigation_trigger`,
`mark_interacted_identity`), and `eligible()` filtered by them. Removed
because `component_identity()` (`tag`/`role`/`name`/`form`/`text`) can't
tell "the same physical widget re-rendering under a churning path" apart
from "a genuinely distinct sibling that happens to share generic text" -
mapadeprofesionales.com's repeated professional cards each render their
own "Conectar"/favorite/share buttons with identical text, and the old
rule let one card's outcome silently decide every other card's, site-wide
for a proven navigation trigger. Every component now gets its own real
attempt, tracked only by exact `path` (`InteractionTracker.is_interacted`).

Deliberately not a full revert of the mechanism this section replaced -
`component_identity()` and `canonicalize_inventory` below (the *graph
relation* / family-clustering side of identity) are kept; only the
*interaction-skipping* use of identity is gone. The tradeoff this
undoes was real and confirmed live (see the history below) - two known
regressions are the accepted, deferred cost for now:
`tests/test_mechanical_loop.py::test_churning_same_page_widget_converges_instead_of_looping_forever`
(a same-page widget that re-renders under a fresh path on every
interaction no longer converges - no numeric interaction ceiling exists
to bound it, so this now hangs and is skipped rather than run) and
`tests/test_mechanical_loop.py::test_failed_click_that_silently_navigated_is_detected_and_not_retried_after_resume`
/ `test_stale_selector_recovery_does_not_starve_a_later_silent_navigation_check`
(a churning nav link whose click fails is re-attempted once per resume
instead of once ever - bounded by the ordinary requeue give-up ceiling,
so this fails an assertion rather than hanging, and is skipped). See map
#211's Not yet specified for the deferred follow-up: some other signal
(e.g. per-identity multiplicity - how many distinct paths an identity
showed *simultaneously* in one snapshot - only excluding a same-identity
reveal once that many real attempts have happened) that could restore
convergence without reintroducing the mapadeprofesionales.com bug.

**History (why this existed):** confirmed live on austral.edu.ar twice.
A persistent nav-menu link that failed to report a real navigation kept
getting re-attempted forever across resumes, because its exact selector
regenerated on every `discover_page()` reload (`path`-keyed
`tracker.is_interacted` never recognized it as already-tried) - fixed by
remembering its *content* identity site-wide once proven a navigation
trigger. Separately, an interactive book-viewer widget (libro_UA30) kept
the exact same page open for 155+ interactions in one run: a same-page
control (thumbnail strip/page-turn) that re-renders under a fresh path on
every click, so the "append newly-revealed components" step kept
offering each fresh render as genuinely new work - fixed by remembering
interacted content identity per page. Both fixes were already a known,
stated tradeoff even then: two coincidentally-identical-looking but
genuinely distinct components (two "Leer más" cards linking to different
articles, both generically labelled) would also collapse under either
rule. That tradeoff is what issue #214 found unacceptable in practice and
removed - the same shape of collision, just common enough on a real site
(every repeated card's own action buttons) to dominate over the
convergence problem it was solving.

## _canonical_paths

page_key -> {`component_identity()` tuple: the `path` it was first seen
under on that page}. Purely a graph-store bookkeeping concern (which
`path` to *persist* for a component, once its identity is already known
on this page) - unlike the removed interaction-skipping identity sets
above, this was never about whether to *re-offer* a component for
interaction, so issue #214 left it untouched. A same-page reveal can
compute a drifted `nth-of-type` path for a physical instance already
recorded here even when the identity itself is stable (issue #170) - the
first path this identity was ever recorded under stays canonical for the
rest of the page's `record_inventory` calls, so a later drift never
reaches the graph store. Two different professionals' otherwise-identical
"Conectar" buttons still get pinned to their own separate paths here
(distinct DOM instances, distinct `Component` nodes) - this only
re-stabilizes one instance's path across reveals of *itself*.

## canonicalize_inventory

What every `record_inventory` call site (`visitor.py`'s
`_record_discovery`, `outcomes.py`'s `transition_to_new_state` and
`handle_same_page_reveal`, `recovery.py`'s `_reconcile_frontier`) routes
its components through before handing them to the sink - never the raw
list. Rewrites each component's `path` to its `_canonical_paths` entry,
leaving every other field (and the original dict) untouched.

Chosen over teaching `database/ladybug/component.py`'s `HAS_COMPONENT`
`MERGE` to tolerate a drifted-but-same-instance path (the second
question #170 posed): that MERGE staying literal-path-keyed is what lets
it correctly record two *genuinely* different physical positions of a
canonical component as two edges: teaching it to collapse "close enough"
paths would risk collapsing those too. Pinning the path before it ever
reaches the store keeps that MERGE's contract simple and puts the
identity-vs-drift judgment in the one place (`Frontier`) that already
owns `component_identity()`-based reasoning.

Deliberately never mutates `component["path"]` in place, and every
caller keeps using the original components list (not this method's
return value) for anything except the `record_inventory` call itself -
the live `path` is still what a frontier item needs to actually target
the real element for a click/fill; only the copy persisted to the graph
store is pinned to the canonical one.

## eligible

Build a fresh interaction frontier from a page's components: visible and
not already interacted (per the `InteractionTracker` passed in, exact
`path`). Returns the frontier plus the set of paths it contains, since
every caller needs both - `visit()`'s own initial frontier build and
`outcomes.py`'s `transition_to_new_state` rebuild both call this instead
of duplicating the list comprehension.
