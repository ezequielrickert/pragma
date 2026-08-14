# `spiders/orchestration/mechanical_loop.py`

## module

Phase 2 of the crawl4ai migration: the mechanical, exhaustive-but-bounded
interaction loop that replaces the old per-step LLM decision loop
(`SimplePRDGenerator._execute_loop`). Fill values default to a
deterministic placeholder (`fill_values.default_placeholder_fill_value`)
but accept a real AI-backed one
(`fill_value_agent.make_ai_fill_value_fn`, Phase 4) via
`MechanicalCrawlerConfig.fill_value_fn` - the only AI call in the crawl
itself, everything else the migration adds is post-hoc (Phase 5).
Page/component state is tracked in-memory by default
(`InMemoryInteractionTracker`) or via `GraphStore` when a `sink` is
supplied (Phase 3, `graph_sink.py`).

Two frontiers, composed but never conflated (per the plan):
- **URL frontier**: a plain FIFO queue of discovered-but-not-visited URLs,
  fed by every page's extracted links. No model decision needed - visited
  in deterministic discovery order. Owned by `MechanicalCrawler` itself.
- **Component/interaction frontier**: per page, every *visible*,
  not-yet-interacted-with component, capped by `element_budget` per page
  (the backstop against a pathological reveal-chain, not a normal-case
  limiter - default generous). A click/fill that changes the DOM on the
  *same* URL gets its newly-revealed components appended to the same
  pass's frontier (still budget-capped); a click/fill that navigates to a
  *different* URL gets that URL queued onto the URL frontier instead of
  being followed inline - avoiding a depth-first recursive blowup is the
  whole reason interaction and navigation are handled as two separate
  frontiers rather than one. Owned by `PageVisitor` (`page_visitor.py`) -
  `MechanicalCrawler` never touches a single page's component frontier
  directly, only hands it a URL to visit.

## MechanicalCrawlerConfig

Every tuning knob `MechanicalCrawler` accepts beyond its two core
collaborators (`crawler`, `tracker`) - bundled into one object (mirroring
`Neo4jConfig` in `database/neo4j_graph_store.py`, and
`Crawl4AICrawlerConfig` in `crawl4ai_crawler.py`) instead of a long
constructor argument list.

- `element_budget`: Per-page cap on the component/interaction frontier -
  a backstop against a pathological reveal-chain, not a normal-case
  limiter (default generous).
- `fill_value_fn`: How to choose a value for a "fill" (text-input-like)
  component. Defaults to a deterministic placeholder; pass
  `fill_value_agent.make_ai_fill_value_fn(agent)` for a real AI-backed
  one - the only AI call in the crawl loop itself.
- `max_pages`: Overall cap on distinct pages visited, regardless of route
  shape. `None` means unbounded.
- `sink`: Live `GraphStore` writes as the crawl happens (Phase 3). `None`
  keeps Phase 2's behavior (no persistence) - see `graph_sink.py` for
  what each call actually writes and why it's not folded into `tracker`
  itself.
- `max_passes_per_page`: Backstop against a pathological page whose
  interactions keep revealing genuinely new content faster than
  `element_budget` can keep up with (an infinite-scroll/live-chat-style
  page) - together, `element_budget * max_passes_per_page` is the real
  total-interactions-per-page-visit ceiling.
- `max_visits_per_route_shape`: Backstop against a site that mints a
  fresh, per-visit-token URL (e.g. `/o/<random-hash>`) on essentially
  every top-level visit - confirmed live on empanad.app. `route_shape()`
  collapses same-shaped URLs so this can bound "how many instances of
  this kind of page" get a full visit, independent of `max_pages`.
  Default 1: an ordinary site has no repeated route shapes at all, so
  this never fires.
- `page_concurrency`: Number of `_worker` coroutines draining the URL
  frontier concurrently.
- `state_transition_overlap_threshold`: Below this fraction of a page's
  known components surviving a same-URL DOM change, `PageVisitor` treats
  it as an in-page *state transition* (a new graph node) rather than an
  ordinary reveal - see `component_matching.component_overlap_ratio`'s
  doc for the empanad.app case this exists for. 0.5 is deliberately
  generous - a real reveal barely touches the ratio at all, so this only
  fires on a genuine near-total replace.
- `base_url`: Scope boundary for the URL frontier (see `_enqueue`) -
  `is_in_scope()` compares hosts only. `None` (default) means "use
  `crawl_site()`'s own start_url" - only needed when a caller wants a
  *different* scope boundary than where the crawl happens to start (e.g.
  starting a few pages deep but still scoping to the site root).
- `allow_subdomains`: Passed through to `is_in_scope()` - whether a
  subdomain of `base_url`'s host counts as in-scope.

## session_recycle_after

How many visits a worker's browser tab carries before `_worker` closes
and rebuilds it. See `_recycle_session_if_due` below for the measured
cause this exists for. `None` disables recycling entirely (useful for a
crawler fake in a test that doesn't implement `close_session` at all,
or a short crawl where the growth this bounds never gets large enough to
matter). Default 15, picked directly from a live measurement against
austral.edu.ar: recycling every 15 navigations reliably reset JS heap to
single-digit MB and event listeners to double digits each time, well
before either climbed anywhere near the growth that correlated with
multi-second navigation stalls in an unrecycled run.

## MechanicalCrawler

Drives `Crawl4AICrawler` through a full site crawl with no per-step AI
decision: every page reachable via links gets visited (`PageVisitor`, via
`_worker`), every visible not-yet-interacted component on each page gets
clicked or filled, up to `element_budget` interactions per page per pass.
This class owns the *site*-level URL frontier and worker orchestration;
the per-page interaction state machine lives in `PageVisitor`
(`page_visitor.py`).

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
- Each worker owns its own `session_id` (`f"worker-{worker_id}"`, see
  `_worker` below) for its entire lifetime, not one per page - so
  concurrent visits don't share a live browser page/session with each
  other; they only share the crawler's underlying browser *process* -
  relying on `crawl4ai`'s own multi-session support for that isolation.
- Everything else - the component/interaction frontier within one page
  visit, the stale-selector resync, route-shape bounding - is per-page,
  single-page-at-a-time logic already, so concurrency at the *page*
  level doesn't change any of it.

## tracker-default

A caller that wires a `sink` almost always wants the matching
GraphStore-backed tracker too (same graph_store/site) - defaulted here so
a caller doesn't have to construct `GraphStoreInteractionTracker` by hand
every time. An explicit `tracker` always wins (e.g. tests that want a
sink's writes recorded but an isolated in-memory tracker for the consult
check).

## url_frontier

`asyncio.Queue`, not a plain deque: `crawl_site`'s worker(s) need to
`await` for a new item rather than busy-poll, and `.join()` is what lets
`crawl_site` know every enqueued item (including ones enqueued *during*
another item's processing) has been fully handled, with no separate "is
anything still in flight" bookkeeping of its own - see `crawl_site`.

## in_flight

clean_url keys a worker is *currently* mid-visit on - a second, narrower
guard than `_queued`, needed specifically because the
interrupted-navigation follow-up requeue (see `_worker`) deliberately
bypasses `_enqueue`'s `_queued` dedup (it has to: the page it's resuming
is, by definition, already in `_queued`). That bypass has no way to know
whether some *other*, unrelated page redirected to the exact same
destination and already requeued it too - confirmed live on a real crawl
(mapadeprofesionales.com, `page_concurrency=10`): many distinct pages'
own "log in" links all redirect to the identical `/login` URL, each
interrupted pass independently calls `put_nowait()` for it, and two idle
workers ended up running `PageVisitor.visit()` for the identical
clean_url/session_id at the same time - a real race on the same live
crawl4ai browser session (crawl4ai keys its own session cache by this
exact string), not just a debug-log cosmetic issue: the *visible* symptom
was the debug_log page-markdown snapshot being overwritten mid-flight by
whichever worker's write landed second, silently losing the other's.

## errors

Every failed interaction across every page visited so far - delegates to
`PageVisitor`, the actual owner of this state (see
`docs/dev/spiders/orchestration/page_visitor.md` for why it persists across visits
within one crawl).

## _enqueue-scope-gate

The single choke point every discovered URL passes through (a plain
link, a follow-up-pass requeue, or a real navigation's destination all
call this), so this one check covers every way the crawl could otherwise
wander off-site: a link to an external domain, or a click/redirect that
lands there (see `PageVisitor._handle_physical_navigation`, which calls
this with `new_state.url` - an out-of-scope destination there is still
correctly recorded as a navigation edge, just never itself
visited/crawled further). `self.base_url` is set by `crawl_site()` before
its own first `_enqueue()` call if not given explicitly.

## _enqueue_links

Queue every http(s) href onto the URL frontier - shared by both the
initial-discovery call site and every same-page-reveal call site in
`PageVisitor` (see Phase 0's ghost-node fix), so a link that only exists
inside a revealed dropdown/menu gets queued exactly like one present on
initial load. Safe to call repeatedly for the same links - `_enqueue`'s
own dedup guard makes this idempotent.

## crawl_site

Crawl every page reachable from `start_url`, `self.page_concurrency`
pages at a time.

Runs that many `_worker()` tasks pulling from the shared `asyncio.Queue`
frontier, then waits on `_url_frontier.join()` - which only returns once
every enqueued item (including ones enqueued *while* another item is
still being processed, e.g. links discovered on a page a worker is
mid-visit on) has had a matching `task_done()` call. That's what makes
this safe with concurrency > 1 without any extra "is anyone still about
to enqueue more work" bookkeeping: a plain `while queue: ...` loop (Phase
2's original shape, still exactly what runs when `page_concurrency=1`,
one worker, one item at a time) can't tell "frontier is momentarily empty
because we're done" apart from "frontier is momentarily empty because
another worker is about to add more" - `Queue.join()`'s unfinished-task
count is exactly the fact needed to disambiguate the two.

## _recycle_session_if_due

Closes `browser_session_id`'s tab once it's carried `session_recycle_after`
visits, resetting the counter to 0; a no-op (return unchanged) below that
threshold, and best-effort via `getattr` the same way `PageVisitor` used
to duck-type session closing - a crawler fake that doesn't implement
`close_session` (most of `tests/test_mechanical_loop.py`'s fakes) just
never recycles, same as `session_recycle_after=None`.

**Why this exists at all**, confirmed by bypassing crawl4ai entirely and
driving raw Playwright directly against austral.edu.ar: a single tab kept
alive across 50 real, distinct page navigations (no repeats) climbed from
~9MB JS heap / ~90 DOM event listeners to ~700MB / ~11000 listeners,
monotonically, never resetting - a plain `page.goto()` to a *different*
URL does not free this, because the growth comes from the site's own
client-side scripts (ads/analytics/GTM tags, effectively universal on
real WordPress sites) holding references across the navigation, not from
anything this codebase keeps around. Chrome's own garbage-collection
pauses for a heap that size landed exactly on the slowest navigations
observed in that same run (a 9.15s navigation coincided precisely with
heap collapsing from 745MB back to 264MB mid-request) - this, not
anything in this project's Python state or crawl4ai's session/context
bookkeeping, is what produced the "grows from ~1s to 15-40s over a long
crawl" symptom reported live.

Closing and reopening just the *page* - proven directly against the same
real site, same URL list, with `context.new_page()` swapped in for
`context.close()` - reset heap to single-digit MB and listeners to double
digits every single time it ran, with cookies/localStorage/consent-banner
state surviving intact (they live on the *context*, untouched by a
page-level recycle) and no context-rebuild cost paid on every page the
way per-visit closing (`docs/dev/spiders/browser/crawl4ai_crawler.md#close_session`,
approach 2) did. `close_session` here is the same underlying
`kill_session` call as that abandoned approach - the difference is
entirely in *how often* it runs: once every `session_recycle_after`
visits instead of once per visit, which is what keeps its context-rebuild
cost rare enough to not matter while still bounding heap/listener growth
well before it becomes a real slowdown.

## _worker

One concurrent visitor - pulls a URL, visits it, requeues or marks it
visited exactly like the old single-loop body did (see the removed
`crawl_site` loop this was extracted from). Runs forever until cancelled
by `crawl_site` right after `_url_frontier.join()` returns, at which
point every worker is guaranteed to be idly blocked on
`_url_frontier.get()` (never mid-visit) since `join()` only completes
once the queue is fully drained.

Builds one `browser_session_id` (`f"worker-{worker_id}"`) up front and
passes the same value to every `PageVisitor.visit()` call this worker
ever makes, across every URL it dequeues for the rest of the crawl - not
a fresh id per URL. This is what keeps a crawl's open browser-tab count
at `page_concurrency` instead of growing by one per page. Tracks
`visits_since_recycle` alongside it and runs `_recycle_session_if_due`
after every visit - see that section below for why a reused-forever tab
still isn't the end state.

Cap-reached branch: drains the rest of the frontier without visiting so
`.join()` can still complete. A *soft* bound once `page_concurrency > 1`
(see `MechanicalCrawler`'s own doc): concurrent workers can each pass
this check before either increments the counter below.

In-flight branch: another worker is already actively (re-)visiting this
exact clean_url - a duplicate dequeue, not new work (see `in_flight`
above for how this happens even though `_enqueue`'s own dedup guard
exists). Drop it rather than run a second concurrent
`PageVisitor.visit()` for the identical session - the in-flight worker
already owns finishing this page, including its own follow-up requeue if
it gets interrupted again; dropping this duplicate loses no coverage,
only the redundant/racy second attempt.

## _worker-requeue

Pass was cut short mid-frontier by a real navigation - this page is not
yet fully explored. Re-queue `result.resolved_url` directly (bypass
`_enqueue`'s dedup guard, which would otherwise refuse a URL already in
`_queued`) rather than marking it visited. This is the *only* case that
needs a fresh `discover_page()` call: the session's live page has
physically moved to a different URL, so there's no "same session" left
to resume - "session" here means a live DOM state to keep interacting
with, not the underlying browser tab, which stays this worker's own
`browser_session_id` (see `_worker` above) regardless of which URL gets
requeued or which worker eventually dequeues it. Budget exhaustion (see
`PageVisitResult.budget_exhausted_with_frontier_remaining`) is handled
entirely inside `PageVisitor.visit`'s own internal round loop instead,
deliberately *without* ever re-navigating - a fresh navigation resets any
same-page DOM state a reveal depends on (confirmed empirically:
re-navigating after a budget-exhausted pass reset a reveal-chain's
trigger back to its pristine unclicked state, but the tracker still
correctly remembered it as already-interacted from the first pass and
skipped it - permanently stranding everything downstream of that
trigger). A page whose frontier still isn't drained even after
`max_passes_per_page` internal rounds simply stays Pending (see
`PageVisitor.visit`) rather than being requeued here.

`resolved_url`, not the original `url` this worker popped: see
`docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`
for the real bug this fixes on a redirecting entry point (re-requesting
the original literal string re-triggers a *fresh* redirect instead of
returning to this in-progress page).

This requeue is safe with respect to session cleanup - see
`docs/dev/spiders/orchestration/page_visitor.md#visit-session-close` for why a resumed
visit never needs the old, already-closed session back.
