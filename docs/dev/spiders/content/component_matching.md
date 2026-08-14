# `spiders/content/component_matching.py`

## module

Split out from `mechanical_loop.py` because these are pure functions over
`discover_components.js`'s component dicts - no crawl state, no I/O -
reused across several of `PageVisitor`'s recovery paths (stale-selector
resync, state-transition detection) that don't otherwise share anything
with each other.

## FILLABLE_INPUT_TYPES

Component tags/input_types the mechanical loop treats as "type into," not
"click" - matches `PlaywrightScraper`'s own `fill()` target shape (a
text-like input, a textarea, or a select). Checkbox/radio/button-typed
inputs are click targets even though they're `<input>` tags.

## is_element_not_found

Whether `exc` is specifically the "selector didn't resolve to a live
element" failure `crawl4ai_crawler.py`'s `click()`/`fill()` raise (message
literally contains "element not found") - as opposed to some other
interaction failure (a JS exception, a network issue). Only this specific
case triggers `mechanical_loop.py`'s stale-selector resync: an id-based
`path` that no longer matches anything is the one failure mode a fresh
same-URL re-discovery can actually recover from; other failures get no
special handling and fall through to the existing record-and-continue
behavior.

## component_identity

Content-based identity for a component - stable across a DOM remount that
reassigns ids (hence `path`) but leaves what the element actually *is*
unchanged. Deliberately doesn't include `path`/`attributes.id` (the very
thing a remount invalidates) or `rect` (position can shift for unrelated
layout reasons); `(tag, role, name, form, text)` is already what
`discover_components.js` extracts for every component, so this needs no
new discovery data.

## component_signature

Stable, order-independent fingerprint of a component snapshot's *shape* -
a short hash of the sorted set of `component_identity()` tuples for every
*visible* component. Used to derive a `state_key` for an in-page SPA
state transition (see `PageVisitor.visit`'s "Same-URL DOM change"
branch): two visits that land on the same underlying screen (e.g.
re-crawling the same "start order" transition from a fresh session)
produce the same signature and collapse to the same graph node - the same
"canonical identity, not a raw counter" discipline `route_shape()`
already applies to session-token URLs (see
wiki/graph-based-crawl-tracking.md).

## state_transition_key

Canonical GraphStore/tracker key for an in-page state reached without any
URL change - see `component_signature`.

## component_overlap_ratio

Fraction of `before`'s *visible* components (by content identity,
`component_identity`) that still exist in `after`. This is the signal
`PageVisitor.visit` uses to tell an ordinary same-page *reveal* (a
dropdown opens - nearly everything from `before` is still there, plus a
few new items) apart from a genuine in-page *state transition* (the whole
screen was replaced - almost nothing from `before` survives).

Confirmed live on empanad.app (see `debug_logs/`): clicking "start order"
never navigates (`navigated: False` throughout) but the component count
swings 3 → 26 → 0 → 11 across one session, and the saved page markdown
collapses to near-nothing mid-pass - a full-screen replace, not a widget
opening. The pre-existing "same-URL DOM change" handling assumes the
*reveal* shape (`find_revealed_options`, append-to-frontier); treating a
full-screen replace the same way would merge several human-distinguishable
screens into one graph node's component ledger, indistinguishable in the
final PRD from a page that never changed.

Returns `1.0` (never a transition) when `before` has no visible
components to compare against - a vacuous "before" snapshot is not itself
evidence of a transition, and this project's decline-not-override
discipline (wiki/graph-based-crawl-tracking.md) says a weak/absent signal
should never trigger the riskier branch.

## remap_stale_frontier

Reconcile `remaining` (not-yet-attempted frontier items, built from a
now-possibly-stale snapshot) against `fresh_components` (a just-resynced,
authoritative snapshot of the current DOM) after an "element not found"
failure - see `PageVisitor.visit`'s except-block doc for when this runs.

Three outcomes per remaining item:
- Its `path` still resolves in the fresh snapshot (untouched by whatever
  remounted) - kept as-is.
- Its `path` doesn't, but a component with the same content identity
  (`component_identity`) does - very likely the same logical element
  under a reassigned id; kept with `path` swapped to the fresh one.
- Neither - genuinely gone (removed from the page, or no longer visible
  in a way this snapshot would show); dropped, and its path returned
  separately so the caller can record it as `stale`, not silently lose it.
