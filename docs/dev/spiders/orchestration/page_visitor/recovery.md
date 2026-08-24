# `spiders/orchestration/page_visitor/recovery.py`

## module

Reconcile state after an ambiguous or failed interaction (a stale
selector, or a session that silently moved without reporting it), plus
one deliberate-not-ambiguous case: hopping the browser back after a
*successful* click landed on a destination the crawl already knows about.
Split out of `PageVisitor` - one responsibility, independent of the normal
success-path bookkeeping `outcomes.py` owns.

## NavigationRecovery

Takes `crawler`/`tracker`/`enqueue_url`/`enqueue_links`/`sink`/the shared
`Frontier` as constructor dependencies - `PageVisitor.__init__` is the
composition root that wires these once per instance.

## _reconcile_frontier

Shared second half of `recover_stale_frontier` and `return_to_origin`
below: both obtain a fresh `PageState` some other way (a no-op resync vs.
a real navigation) and then need the identical reconciliation against it -
see
`docs/dev/spiders/content/component_matching.md#remap_stale_frontier` for
the remap itself.

Mutates `frontier` in place (slice-replaces `frontier[idx:]` with the
reconciled remainder, same length or shorter) and adds every surviving
item's (possibly new, post-remap) path to `seen_paths_this_pass` -
without this, a remapped item's new path isn't yet known to the pass's
own "is this genuinely new" dedup check, so the very next successful
reveal's append-new-components step
(`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_same_page_reveal`)
would see that same path as unseen and queue a duplicate entry for a
component already sitting in `frontier`.

## recover_stale_frontier

Resync current DOM state after an "element not found" failure and
reconcile the remaining, not-yet-attempted frontier against it via
`_reconcile_frontier` - see
`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-except-stale-resync`
for when this runs.

Returns the fresh component snapshot to become the pass's new
`known_components` baseline, or `None` if the resync call itself failed
(network/crawl4ai error) - frontier is left untouched in that case, same
as any other best-effort recovery that couldn't get fresh data to act on.

## return_to_origin

The physical-navigation counterpart to `recover_stale_frontier`: called
from `visit`'s physical-navigation branch, always, right after
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation`
records the edge/enqueues the destination - known destination or not, the
pass doesn't need to stop, only the browser, which really did navigate
away, needs to come back. (Originally known-destination-only - see that
method's own "Update" note for why the distinction was dropped.)

Steps back via `Crawl4AICrawler.go_back` (browser history, not a no-op
resync - the session is actually on the wrong page - and deliberately not
a fresh `discover_page` either, see that method's own docstring for why:
a full navigation would re-request the target server for a page this
session just rendered a moment ago) and reconciles via
`_reconcile_frontier`, same as `recover_stale_frontier`. Returns the fresh
`PageState` itself (not just its components) - unlike
`recover_stale_frontier`, the caller also needs the new `page_literal` to
replace its own.

Takes `page_literal` (the caller's expected destination) as an explicit
parameter and checks the result against it: `go_back` can return
successfully - no exception - without the session actually being back on
the expected page (an empty history stack, or a client-side router
swallowing the `popstate` event), and continuing to interact under
`page_key` against the *wrong* live page would silently misattribute
whatever happens next. Confirmed live on austral.edu.ar
(FETCH time for a repeated request to the same URL climbing from 2.77s to
4.21s in one observed run - the target's own rate limiting, not a crawl4ai
timeout) that a full re-navigation was measurably provoking exactly the
load-sensitivity `TargetLoadThrottle` exists to react to, which is what
motivated replacing the `discover_page` call this method used before with
`go_back`.

Returns `None` if `go_back` itself raised (presumed-dead session, no
further request attempted) or if `go_back` landed on the wrong page *and*
the `_reload_origin` fallback below also failed to land on `page_literal`
- either way `visit`'s caller then has no live page left to keep
interacting with and falls back to the ordinary interrupted path
(`result.interrupted_by_navigation = True`, stop, requeue the origin for a
later pass, which reaches it via a real `discover_page` instead) rather
than continue against nothing. Covered by
`tests/test_mechanical_loop.py::test_known_destination_return_navigation_failure_falls_back_to_interrupted_path`
(the raise case, no reload attempted), for the common success path
`tests/test_mechanical_loop.py::test_known_destination_resume_uses_go_back_not_a_fresh_navigation`,
and for the wrong-landing recovery path
`tests/test_mechanical_loop.py::test_return_to_origin_reloads_after_go_back_lands_wrong`.

## _reload_origin

`return_to_origin`'s fallback for the one case `go_back` alone can't
recover from: a client-side router that swallows the `popstate` event a
history navigation fires, stranding the session on the wrong URL, or on
`page_literal` itself but still rendering whatever the triggering click
crashed into (a React error boundary, say - a route change alone doesn't
remount past one). Issue #211's motivating case: mapadeprofesionales.com's
"Ir al mapa" button crashes the SPA into an error-boundary state that
`go_back`'s history navigation doesn't clear, stranding every frontier
component after it in DOM order - including the nested card→modal
interaction the map exists to reach - behind a pass that would otherwise
give up immediately.

A real `discover_page` navigation, same as `return_to_origin` used
exclusively before the austral.edu.ar finding motivated switching to
`go_back` - see that method's own docstring. Only reached once `go_back`
has already proven history navigation alone won't do it, so the one extra
request this costs is paid rarely, not on the common path
`test_known_destination_resume_uses_go_back_not_a_fresh_navigation` still
guards. Navigates to `page_url` (the origin's real, schemed URL, threaded
through `return_to_origin` for exactly this) rather than `page_literal`
(`clean_url`'s stripped form, kept only for the landing check).

Returns the fresh `PageState` on a clean landing, or `None` if the
navigation itself raised or landed somewhere other than `page_literal` too
- `return_to_origin` treats either the same as its own failure.

## check_for_silent_navigation

After an interaction failure that wasn't cleanly identified as either a
stale-selector remount (`component_matching.is_element_not_found`) or a
successful navigation (the success branch's own `new_literal !=
page_literal` check), check whether the live browser session actually
moved anyway.

Confirmed live on austral.edu.ar: a real `<a href>` click can physically
navigate the browser, but if the destination page is slow enough to
settle that reading back this module's own success marker times out
first, `Crawl4AICrawler._interact()` raises a plain failure with no
`resulting_url` at all - from `visit`'s point of view this looks
identical to an ordinary broken selector, so the loop kept attempting
every remaining frontier item against a page the session had already
left, each one *also* doomed the same way, for as many components as the
original page had - confirmed live: 90+ minutes, one single `visit()`
call that never returned.

Uses `resync()` - the same no-op-`js_code` re-discovery
`recover_stale_frontier` already uses - purely as a way to read the live
session's *current* URL; best-effort, since the destination page might
still be slow enough that even this call fails, in which case the caller
falls back to its pre-existing behavior (this is a strict improvement
over that fallback, never worse).

Returns the live session's current URL if it differs from `page_literal`
(a real, silently-missed navigation), or `None` if the session is
confirmed still on the same page, or if the check itself couldn't
complete.

## handle_possible_silent_navigation

Called from `visit`'s except-block for a failure that isn't the
stale-remount case - see `check_for_silent_navigation` above for the
real symptom this fixes. Performs the check and, if it confirms a silent
navigation, all the same bookkeeping the success-branch's navigation case
does (enqueue the destination, mark `interrupted_by_navigation`,
remember the content identity via `Frontier.mark_navigation_trigger`,
record the edge) - kept as its own method purely to keep `visit` itself
from growing an even deeper nested branch.

Returns whether `visit`'s interaction loop should stop (`True`) -
mirroring the success branch's own `break`.

Deliberately does *not* run the known-destination check
`handle_physical_navigation` does - this path only fires alongside a
genuinely failed interaction (an ambiguous read-back, not a clean
success), a rarer and already-harder-to-reason-about case where resuming
in place adds risk the ordinary successful-click path doesn't have. Always
stops the pass, same as before this distinction existed.
