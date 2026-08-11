# `src/crawlers/visit_result.py`

## module

Split out from `mechanical_loop.py` because these are plain result records
with no crawl behavior of their own - callers (`crawl_site`, `graph_sink.py`,
tests) only ever read them.

## ComponentInteraction.action

`"click"` | `"fill"` for a real attempted interaction; `"discover"` for a
page that never even loaded (`discover_page` itself raised - see
`docs/dev/crawlers/page_visitor.md#_discovery_failed`), recorded with
`path=""` since there's no specific component to point at. Not an enum -
this is the one place outside `PageVisitor` that cares which value it
holds (a crawl's error report grouping "pages that never loaded" apart
from "components that failed once loaded"), so a plain `str` was enough.

## ComponentInteraction.stale

True when this entry represents a frontier item dropped by
`component_matching.remap_stale_frontier` (an "element not found" failure,
resynced, and still not resolvable by content identity) rather than a real
attempted-and-failed interaction. Kept distinct from `error` so a
human/consumer reading `errors`/`page_results` can tell "we tried and the
site rejected it" apart from "a DOM remount stranded this component and we
gave up looking for it in this pass" - same "don't silently lose it"
discipline as `interrupted_by_navigation`.

## PageVisitResult.resolved_url

The literal, already-redirect-resolved URL this visit actually landed on
(`state.url` from `Crawl4AICrawler.discover_page` - see its
`_resolved_url` for why this can differ from the URL requested).
Deliberately NOT `url` above (which is the *canonical*, `route_shape()`-
collapsed storage key - see `PageVisitor.visit`'s docstring) and NOT
necessarily identical to whatever literal string this visit was
originally requested with either. This is what a follow-up-pass requeue
must re-request - see `interrupted_by_navigation` below for why
re-requesting the *original* literal string is a real bug on a
redirecting entry point.

## PageVisitResult.interrupted_by_navigation

True when a click/fill mid-pass navigated the session's page away from
`url` before the frontier was drained - see `PageVisitor.visit`'s
docstring for why the pass stops immediately rather than continuing to
act against selectors that belonged to a page the session has physically
left. `crawl_site`/`_worker` re-queue `resolved_url` (not the original
request) when this is set, so the untouched remainder of the frontier
gets a follow-up pass (already-interacted components, including the one
that caused the navigation, are skipped via the tracker next time -
guaranteed forward progress each pass).

**Bug found live on empanad.app, fixed by requeuing `resolved_url` instead
of the original request**: the site's *bare* entry URL
(`https://empanad.app`) redirects to a brand-new `/o/<hash>` session on
*every* visit - not just the first. Re-queuing the originally-requested
literal string (the bare URL) for a follow-up pass meant every such pass
re-triggered a fresh redirect to yet another new hash instead of
returning to the order the first pass was actually working on - confirmed
in a real debug log: a follow-up pass's `before_goto` request for the
literal bare URL landed on a third, completely different order hash,
abandoning the second hash's own still-undrained frontier entirely.
`resolved_url` is what `discover_page` actually landed on after any
redirect the *first* time - re-requesting that directly (a concrete,
addressable resource, not a redirecting entry point) is what actually
returns to the same session/order instead of minting another new one.
For an ordinary, non-redirecting site, `resolved_url` is identical to
what was requested, so this is a no-op there.

## PageVisitResult.state_transitions

Every `state_key` (see `component_matching.state_transition_key`) this
pass switched onto after detecting an in-page SPA state transition (low
component overlap on a same-URL DOM change - see `component_matching.
component_overlap_ratio`). `url` above stays the *first* node this visit
started on; this records every subsequent node reached within the same
continuous session, in order. Empty for the overwhelming majority of
pages (ordinary sites, and SPAs whose same-page changes are ordinary
reveals) - only populated when a real screen-replacement was detected.
