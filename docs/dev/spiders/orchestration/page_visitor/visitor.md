# `spiders/orchestration/page_visitor/visitor.py`

## module

The mechanical crawl loop's single-page interaction state machine - split
out from `mechanical_loop.py`'s `MechanicalCrawler`, which owns the
*site*-level URL frontier/worker orchestration instead. `MechanicalCrawler`
constructs one `PageVisitor` per crawl and hands every dequeued URL to
`visit()`; this module never touches the URL frontier itself, only the
`enqueue_url`/`enqueue_links` callbacks passed in at construction time.

`visit()`'s own state machine is the one responsibility left in this
file - failure-path recovery and success-path outcome bookkeeping are
their own collaborators, see
`docs/dev/spiders/orchestration/page_visitor/recovery.md` and
`docs/dev/spiders/orchestration/page_visitor/outcomes.md`.

## _max_consecutive_unexplained_failures

Circuit breaker for `visit`'s interaction loop - see
`visit-except-circuit-breaker-trip` below for the exact symptom this
bounds (a session parked on a page that never finishes loading makes the
silent-navigation check itself fail the same way every real interaction
does, so nothing else stops the pass from burning the entire remaining
frontier one interaction-timeout at a time). Deliberately small: this
isn't a general exploration limit (the interaction loop has none - see
`visit-frontier-loop` below), it's specifically for a pass that's already
shown it isn't converging.

## PageVisitor

Mechanically interacts with one page's frontier at a time, called once
per URL by `MechanicalCrawler._worker`. Holds `errors` and the collaborator
instances (`Frontier`/`NavigationRecovery`/`InteractionOutcomes`) that
must persist *across* visits within one crawl - constructed once per
`MechanicalCrawler` and reused for every `visit()` call, not a per-visit
throwaway.

## __init__-collaborators

`Frontier` is constructed first and passed into both `NavigationRecovery`
and `InteractionOutcomes` - all three need to agree on the same
navigation-trigger/interacted-identity state for one page_key, so there's
exactly one `Frontier` instance per `PageVisitor`, not one per
collaborator.

`is_known_url` (`MechanicalCrawler.__init__` passes `UrlFrontier.is_known`
bound through - see
`docs/dev/spiders/orchestration/mechanical_loop/frontier.md#is_known`)
only goes to `InteractionOutcomes`, not `NavigationRecovery` - it's a
decision `handle_physical_navigation` makes, not something the recovery
methods themselves need to know.

## _fill_value_cache

`(page_key, component_identity())` -> the value already generated for
that field. Every fillable component reappears at least twice within one
`visit()` (the pre-interaction snapshot and the post-interaction
re-extraction both walk the same, unchanged form), and the same field
shape can also recur across separate passes on one page - without this,
`fill_value_fn` (a live AI call by default - see
`docs/dev/spiders/content/fill_value_agent.md#make_ai_fill_value_fn`) reruns for
a field this pass has already generated a value for. Scoped to one
`PageVisitor` instance (one crawl run), not persisted - see `_fill_value`.

## _fill_value

Look up `_fill_value_cache` before calling `fill_value_fn`; store the
result on a miss. Keyed by `(page_key, component_identity(component))`,
not `component_identity(component)` alone - two different pages can share
a field shape (e.g. every page's "email" input), and caching across pages
would incorrectly reuse one page's generated value for an unrelated
field on another.

## _discovery_failed

**Why this exists**: `discover_page` raising was never caught anywhere in
this method - confirmed as a real, live production hang, not a
hypothetical: 200+ pages into a real austral.edu.ar crawl, one page
failed discovery (`Blocked by anti-bot protection: Structural: no <body>
tag`), the exception propagated straight out of `visit()`, and with
nothing catching it the single worker (`page_concurrency=1`, the
default) simply died mid-`while True` loop - not a clean crash, a silent
one, since `_worker`'s only wrapping is a bare `finally:
self._url_frontier.task_done()`. Every other URL still sitting in the
frontier (including ones enqueued by pages already visited, so likely
more than one) then had no live worker left to ever dequeue it, and
`crawl_site`'s `await self._url_frontier.join()` waits for a
`task_done()` count that can now never reach zero - a permanent hang,
not a crash with a traceback, which is why it read as "stuck, no advance
at all" rather than an error.

Turns that exception into an ordinary, non-`interrupted_by_navigation`
`PageVisitResult` instead - `_worker`'s existing else-branch (see
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker`) already
knows what to do with one of those: mark the URL visited and move on,
exactly "skip this one page, don't retry it forever" with no new code
needed on the `MechanicalCrawler` side. `page_key = route_shape(url)` -
the requested URL, not a resolved one, since discovery never got far
enough to resolve anything. Recorded into `self.errors` as a
`ComponentInteraction` with `action="discover"` (a third action value
alongside `"click"`/`"fill"` - see
`docs/dev/spiders/orchestration/visit_result.md#componentinteractionaction`)
so a crawl's error report shows *which* pages never even loaded, not just
which components failed once loaded.

## visit

Visit `url` and mechanically interact with its frontier.

`session_id` names the physical browser tab crawl4ai should navigate;
defaults to `url` (a throwaway tab, one per call) so a bare `visit(url)`
still works standalone, e.g. in tests. `MechanicalCrawler` instead passes
one stable value per worker, reused across every URL that worker visits,
so a crawl's open-tab count stays at `page_concurrency` rather than
growing by one per page - periodically recycled by the worker, not by
`visit()` itself. See
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker` and
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_recycle_session_if_due`.

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
See `docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`
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

## visit-step

One `VisitStep` sequence per pass, shared by an interaction and the
requests it fired - a local variable, not instance state: a single
`PageVisitor` is shared across concurrent workers, so a counter on `self`
would interleave two pages' steps into one nonsense trace.

## record_page_network

Only recorded once, right after discovery - not on the post-interaction
path: those requests already belong to the component that fired them, so
attributing them to the page itself again would double-count.

## visit-known-components

Most recently known full component snapshot for this pass - starts as
the initial discovery, updated after every same-page reveal so a later
reveal's `find_revealed_options` diff compares against the immediately
preceding snapshot, not the page's original load state (otherwise a
cascading reveal - A reveals B, an interaction inside B reveals C - would
spuriously report B's own already-revealed content as "new" again when C
appears).

## visit-content-identity-exclusions

See `docs/dev/spiders/orchestration/page_visitor/frontier.md` for why a
freshly-reloaded page's own churned selectors can't be caught by the path
check alone - `Frontier.eligible()` is what applies both the
navigation-trigger and interacted-identity exclusions here.

## visit-frontier-loop

No numeric ceiling on how many components one visit interacts with -
removed deliberately, since this project's priority is a complete graph
over a bounded-worst-case runtime (see
`docs/dev/spiders/orchestration/mechanical_loop/config.md#module`'s note
on why `element_budget`/`max_passes_per_page` no longer exist). The loop
terminates when the frontier itself is exhausted (`idx == len(frontier)`)
or one of the three `break` paths below fires - convergence for an
ordinary page comes entirely from `Frontier`'s content-identity dedup
(`docs/dev/spiders/orchestration/page_visitor/frontier.md`), not from any
cap in this file. A page whose DOM genuinely regenerates distinct new
component identities forever (an infinite-scroll or live-chat-style feed)
has no backstop here and will not terminate - an accepted, not a
mitigated, tradeoff.

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
  `docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities`),
  so every future resume kept re-discovering and re-failing on it,
  indefinitely, even though the very same component had already been
  proven, once, to navigate away. Two independent guards is what actually
  makes both recoveries available within one pass, exactly as each was
  designed to be used on its own.
- `consecutive_unexplained_failures` - circuit breaker, independent of
  both guards above. Confirmed live on austral.edu.ar: a session that
  lands on a page whose own `domcontentloaded` never fires (a WAF holding
  the response open) makes
  `NavigationRecovery.handle_possible_silent_navigation`'s own `resync()`
  call fail the *exact* same way every subsequent real interaction does -
  the ONE check built to catch "did we silently navigate away" is exactly
  the one guaranteed to also come back inconclusive here, and since it
  only runs once per failure streak, every remaining frontier item then
  gets attempted anyway, each independently burning a full
  interaction-timeout before failing the same way - confirmed live: 40+
  consecutive identical `Timeout 30000ms exceeded` failures over 40+
  minutes, still climbing, on one single page. This counts *consecutive*
  failures that reach this specific branch (not stale-selector remounts,
  which are a different, already-understood recovery) and gives up on
  the pass - not silently, not forever - once continuing clearly isn't
  converging on anything.

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
see `docs/dev/spiders/orchestration/page_visitor/recovery.md#recover_stale_frontier`.

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
the fix, not a retry-count cap: see
`docs/dev/spiders/orchestration/page_visitor/recovery.md#handle_possible_silent_navigation`.

## visit-except-circuit-breaker-trip

The silent-navigation check above is itself just another interaction
against this same session - if the session is genuinely dead (parked on
a page that never finishes loading), that check fails the identical way
every real interaction does, so it can never confirm what it exists to
confirm. Give up on this pass rather than burning the rest of the
frontier the same way, one interaction-timeout at a time - not a
confirmed navigation, but the same recovery (requeue this page for a
fresh visit later - see
`docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`)
is the right honest outcome: this pass isn't converging, and a fresh
session may not be stuck the same way.

## visit-physical-navigation-branch

Real *physical* navigation - the live browser session moved to a
different literal URL, even if it canonicalizes to the same route_shape
(e.g. a "start a new order" flow landing on a fresh `/o/<hash>` every
time - the selectors this pass was built for are still gone either way).
Delegates to
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation`,
which decides whether the destination is already known to this crawl.

An **unknown** destination (`must_stop` is `True`) still stops the pass
right here, same as before this distinction existed: the session's page
has physically left `page_literal`, so no further frontier item from this
pass can be safely acted on, and the whole page gets requeued for a
separate later pass.

A **known** destination doesn't need a separate pass - only the browser,
which really did navigate away, needs to come back.
`docs/dev/spiders/orchestration/page_visitor/recovery.md#return_to_origin`
does that via browser history (`Crawl4AICrawler.go_back` - not a fresh
`discover_page` navigation, and not a no-op resync either) and reconciles
the remaining frontier against whatever DOM state it finds; passed the
current `page_literal` so it can check the browser actually landed back
where expected. On success the loop `continue`s with the fresh
`known_components`/`page_literal` instead of breaking. If the return
fails - `go_back` itself raises, or lands somewhere unexpected - there's
no live page left to act on, so this falls back to the unknown-destination
outcome: `result.interrupted_by_navigation = True`, then `break`.

Confirmed live on austral.edu.ar: without this distinction, a site-wide
nav menu (nearly every page links to nearly every other page) meant
nearly every page's first few interactions were known-destination clicks
that each interrupted the pass anyway - most pages exhausted
`max_requeue_attempts` purely on nav-menu links, marked Failed before
reaching any of their own content.

## visit-state-transition-branch

In-page *state transition*, not a mere reveal - confirmed live on
empanad.app's "start order" button: the physical URL never changes
(`navigated: False` throughout) but the DOM is almost entirely replaced
(3 -> 26 -> 0 -> 11 components across one session). Below
`state_transition_overlap_threshold` component-identity overlap between
the immediately preceding snapshot and this one, treat it like a real
navigation to a *new* graph node instead of merging into this one - a
third identity question beyond page_literal/page_key (see `visit`'s own
doc above): "is this still the same *screen*," answered by DOM-overlap
since the URL gives no signal at all for a client-routed SPA. See
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#transition_to_new_state`
for the actual bookkeeping.

## visit-same-page-branch

Same-URL DOM change - a real, equally-authoritative discovery snapshot in
its own right, not just a source of "new" frontier candidates. See
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_same_page_reveal`.

## visit-record-page-finished

A pass cut short by navigation leaves the page genuinely incomplete. It
must stay Pending for its follow-up pass (see
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#crawl_site`'s
requeue logic and
`docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_finished`),
not be marked Finished here just because *a* pass happened. With no
numeric ceiling on the interaction loop itself (see `visit-frontier-loop`
above), a navigation interruption is now the only way a pass ends without
having drained its own frontier.
`known_components`, not `state.components` (the *initial* snapshot
only) - a page that went through same-page reveals or a state transition
finishes with `page_key`/`known_components` both pointing at whatever
node this pass actually ended on, and the component count recorded
should describe that node, not the first one this visit ever saw.

## why visit() never closes its own session

An earlier version closed `session_id` at `visit()`'s tail, right before
`return result`, once per call. That fixed a real leak (every distinct
URL got its own never-closed browser tab) but, on this project's default
`page_concurrency=1`, forced crawl4ai to tear down and rebuild its one
shared browser context on *every single page* - context creation is far
more expensive than the one leaked page it replaced. `session_id` now
names a tab a worker keeps across many visits (assigned by
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker`,
defaulted to `url` here only for a standalone call), so `visit()` itself
has nothing to close - closing is a *worker*-level decision (how many
visits a tab has carried so far), not something knowable from inside a
single `visit()` call. See
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_recycle_session_if_due`
for where that decision actually lives and why it's needed at all - the
tab isn't merely reused now, it's reused-then-periodically-recycled.
