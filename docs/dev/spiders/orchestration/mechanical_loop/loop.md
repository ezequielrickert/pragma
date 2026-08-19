# `spiders/orchestration/mechanical_loop/loop.py`

## module

The mechanical, exhaustive interaction loop that replaces the old
per-step LLM decision loop. Fill values default to a deterministic
placeholder (`fill_values.default_placeholder_fill_value`) but accept a
real AI-backed one (`fill_value_agent.make_ai_fill_value_fn`) via
`MechanicalCrawlerConfig.fill_value_fn` - the only AI call in the crawl
itself. Page/component state is tracked in-memory by default
(`InMemoryInteractionTracker`) or via `GraphStore` when a `sink` is
supplied (`graph_sink/`).

Two frontiers, composed but never conflated:
- **URL frontier**: a plain FIFO queue of discovered-but-not-visited URLs,
  fed by every page's extracted links. No model decision needed - visited
  in deterministic discovery order. Owned by `frontier.py`'s `UrlFrontier`,
  not this class directly - see that module's own doc.
- **Component/interaction frontier**: per page, every *visible*,
  not-yet-interacted-with component - no numeric ceiling (see
  `docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop`
  for why that cap was removed and what it cost when it existed).
  A click/fill that changes the DOM on the *same* URL gets its
  newly-revealed components appended to the same pass's frontier;
  a click/fill that navigates to a *different* URL gets that URL queued
  onto the URL frontier instead of
  being followed inline - avoiding a depth-first recursive blowup is the
  whole reason interaction and navigation are handled as two separate
  frontiers rather than one. Owned by `PageVisitor`
  (`docs/dev/spiders/orchestration/page_visitor/`) - `MechanicalCrawler`
  never touches a single page's component frontier directly, only hands
  it a URL to visit.

This file itself owns just the *loop* that ties `UrlFrontier` and
`WorkerPacing` together - see `frontier.md` and `worker_pacing.md` for
the two collaborators' own reasons to change.

## MechanicalCrawler

Drives `Crawl4AICrawler` through a full site crawl with no per-step AI
decision: every page reachable via links gets visited (`PageVisitor`, via
`_worker`), and every visible not-yet-interacted component on each page
gets clicked or filled - no cap on how many. This class owns the
*site*-level URL frontier and worker orchestration;
the per-page interaction state machine lives in `PageVisitor`.

`page_concurrency` (via `WorkerPacing`) controls how many pages get
visited at once - `crawl_site` runs that many `_worker()` tasks pulling
from a shared `UrlFrontier` instead of one sequential loop. Raising it is
the biggest lever for a large crawl's wall-clock time: every fixed
per-interaction wait (`Crawl4AICrawler`'s `wait_seconds`/
`interaction_wait_seconds`) overlaps across concurrently-visited pages
instead of serializing - confirmed via a real run's own debug log that
those fixed sleeps, not rendering or network cost, dominate a sequential
crawl's time.

What raising `page_concurrency` changes, precisely:
- `max_pages` becomes a *soft* bound - concurrent workers can each pass
  the "have I hit the cap" check before either increments the shared
  counter, so the crawl can overshoot by up to `page_concurrency - 1`
  pages - a documented, deliberate looseness, not worth a lock for a
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

## __init__-collaborators

`UrlFrontier` and `WorkerPacing` are each constructed from `self.tracker`/
`crawler`/`config` directly - `MechanicalCrawler` is the composition root,
same pattern `PageVisitor.__init__` uses for its own collaborators (see
`docs/dev/spiders/orchestration/page_visitor/visitor.md#__init__-collaborators`).
`PageVisitor` is constructed last, once `self._frontier` exists, so it can
be handed `self._frontier.is_known` bound through as its own
`is_known_url` dependency.

## tracker-default

A caller that wires a `sink` almost always wants the matching
GraphStore-backed tracker too (same graph_store/site) - defaulted here so
a caller doesn't have to construct `GraphStoreInteractionTracker` by hand
every time. An explicit `tracker` always wins (e.g. tests that want a
sink's writes recorded but an isolated in-memory tracker for the consult
check).

## errors

Every failed interaction across every page visited so far - delegates to
`PageVisitor`, the actual owner of this state (see
`docs/dev/spiders/orchestration/page_visitor/visitor.md` for why it
persists across visits within one crawl).

## crawl_site

Crawl every page reachable from `start_url`, `WorkerPacing.page_concurrency`
pages at a time.

Runs that many `_worker()` tasks pulling from the shared `UrlFrontier`,
then waits on `self._frontier.join()` - which only returns once every
enqueued item (including ones enqueued *while* another item is still
being processed, e.g. links discovered on a page a worker is mid-visit
on) has had a matching `task_done()` call. That's what makes this safe
with concurrency > 1 without any extra "is anyone still about to enqueue
more work" bookkeeping: a plain `while queue: ...` loop can't tell
"frontier is momentarily empty because we're done" apart from "frontier
is momentarily empty because another worker is about to add more" -
`Queue.join()`'s unfinished-task count is exactly the fact needed to
disambiguate the two.

## _recycle_session_if_due

Closes `browser_session_id`'s tab once it's carried `session_recycle_after`
visits, resetting the counter to 0; a no-op (return unchanged) below that
threshold, and best-effort via `getattr` - a crawler fake that doesn't
implement `close_session` (most of `tests/test_mechanical_loop.py`'s
fakes) just never recycles, same as `session_recycle_after=None`.

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
way per-visit closing
(`docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#close_session`,
approach 2) did. `close_session` here is the same underlying
`kill_session` call as that abandoned approach - the difference is
entirely in *how often* it runs: once every `session_recycle_after`
visits instead of once per visit, which is what keeps its context-rebuild
cost rare enough to not matter while still bounding heap/listener growth
well before it becomes a real slowdown.

## _worker

One concurrent visitor - pulls a URL, visits it, requeues or marks it
visited. Runs forever until cancelled by `crawl_site` right after
`self._frontier.join()` returns, at which point every worker is
guaranteed to be idly blocked on `self._frontier.get()` (never mid-visit)
since `join()` only completes once the queue is fully drained.

Builds one `browser_session_id` (`f"worker-{worker_id}"`) up front and
passes the same value to every `PageVisitor.visit()` call this worker
ever makes, across every URL it dequeues for the rest of the crawl - not
a fresh id per URL. This is what keeps a crawl's open browser-tab count
at `page_concurrency` instead of growing by one per page. Tracks
`visits_since_recycle` alongside it and runs `_recycle_session_if_due`
after every visit - see that section above for why a reused-forever tab
still isn't the end state.

Two pacing calls at the top of every loop iteration
(`self._pacing.wait_for_memory_headroom()`,
`self._pacing.wait_for_capacity(worker_id)`) - see
`docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md` for
what each one gates on.

Cap-reached branch: drains the rest of the frontier without visiting so
`.join()` can still complete. A *soft* bound once `page_concurrency > 1`
(see `MechanicalCrawler`'s own doc above): concurrent workers can each
pass this check before either increments the counter below.

In-flight branch: another worker is already actively (re-)visiting this
exact clean_url - a duplicate dequeue, not new work (see
`docs/dev/spiders/orchestration/mechanical_loop/frontier.md#in_flight`
for how this happens even though `enqueue`'s own dedup guard exists).
Drop it rather than run a second concurrent `PageVisitor.visit()` for the
identical session - the in-flight worker already owns finishing this
page, including its own follow-up requeue if it gets interrupted again;
dropping this duplicate loses no coverage, only the redundant/racy second
attempt.

## _worker-requeue

Pass was cut short mid-frontier by a real navigation - this page is not
yet fully explored. Re-queue `result.resolved_url` directly via
`self._frontier.requeue()` (bypassing `enqueue`'s dedup guard, which
would otherwise refuse a URL already queued) rather than marking it
visited. This is the *only* case that needs a fresh `discover_page()`
call: the session's live page has physically moved to a different URL,
so there's no "same session" left to resume - "session" here means a
live DOM state to keep interacting with, not the underlying browser tab,
which stays this worker's own `browser_session_id` (see `_worker` above)
regardless of which URL gets requeued or which worker eventually
dequeues it.

With no numeric ceiling on `PageVisitor.visit`'s own interaction loop
(see `docs/dev/spiders/orchestration/page_visitor/visitor.md#visit-frontier-loop`),
navigation is now the only reason a pass ends without having drained its
frontier - so this is the only requeue path left. An earlier version of
this cap tried re-navigating on a cut-short pass instead of requeuing;
that was wrong for the same underlying reason a navigation-interrupted
pass can't simply re-navigate either: a fresh navigation resets any
same-page DOM state a reveal depends on, while the tracker still
correctly remembers earlier interactions as done - stranding everything
downstream of a reveal trigger that a re-navigation silently rewound.

`resolved_url`, not the original `url` this worker popped: see
`docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`
for the real bug this fixes on a redirecting entry point (re-requesting
the original literal string re-triggers a *fresh* redirect instead of
returning to this in-progress page).

This requeue is safe with respect to session cleanup - see
`docs/dev/spiders/orchestration/page_visitor/visitor.md#why-visit-never-closes-its-own-session`
for why a resumed visit never needs the old, already-closed session back.

## visit-counters

`_unique_visits`/`_requeued_visits`/`_gave_up_visits` are split deliberately:
a requeued visit prints exactly like a fresh one in crawl4ai's own output,
so a crawl churning on the same handful of pages is otherwise
indistinguishable from one making progress - separating them is the whole
diagnostic value of `_report_visit`'s per-visit line. `_gave_up_visits`
counts visits `_worker-give-up` below concluded on, distinct from an
ordinary requeue that's still going to be retried.

## budget-nodes

`CrawlBudget.nodes` estimates graph growth (`budget.md#crawlbudget`), not
"pages finished" - unlike `CrawlBudget.pages` (`_worker-budget` below),
it's recorded for every visit regardless of interruption, since
`record_inventory`/`record_page_arrival` already wrote that data to the
store before any interruption could happen. An interrupted pass still
grew the store by exactly that much; only the page itself hasn't
concluded.

## _worker-budget

`CrawlBudget.pages` counts pages *finished* this run - its own docstring.
Only recorded in the branch that already does the rest of "this page
really concluded" bookkeeping (`mark_visited`, `record_route_shape_visit`),
never for a requeued/interrupted pass. Confirmed live: recording it
unconditionally let a site whose anti-bot protection intermittently
blocks requests burn its whole page budget re-requeuing the same handful
of pages - the run reported "budget reached" after barely any real
completions, while hundreds of already-discovered URLs never got a
single attempt.

## _worker-give-up

Once `UrlFrontier.requeue` (`frontier.md#requeue`) refuses to requeue a
page past `max_requeue_attempts`
(`docs/dev/spiders/orchestration/mechanical_loop/config.md#max_requeue_attempts`),
`_worker` marks it concluded the same two ways an ordinary finish does -
`tracker.mark_visited(key)` (so this process never reconsiders it, same
key `is_visited`/`enqueue` check) and `sink.record_page_failed(result.url)`
(so a resumed run doesn't either) - rather than looping `requeue()`
forever on a page that keeps tripping the same block.

## _budget_exhausted

Whether this run is done taking new pages, announcing the reason the first time
it trips so the terminal says why rather than just going quiet.

## _finished_route_shapes

Route shapes a previous run already sampled, read from the graph and handed to
`prime_route_shape_visits` before any enqueue.

## _report_visit

One line per finished visit, naming the worker - with `page_concurrency` above 1,
interleaved progress lines from several workers are otherwise unreadable.

## _resume_urls

The `Pending` pages a previous run left behind. These *are* the saved progress,
which is why `PragmaConfig.fresh` defaults to off - purging deletes them before
this can read them.

## crawl_site-prime

Priming happens **before any enqueue**, because the route-shape gate runs inside
`enqueue`: priming afterwards would let already-sampled shapes back in through
the very calls the gate is meant to filter.

## crawl_site-resume

Resumed URLs are enqueued **after** `start_url`, so the entry point is always
visited first.

They go through `enqueue` rather than straight into the queue, so scope, dedup
and the route-shape cap are re-applied - a stale or now-out-of-scope pending URL
is filtered here rather than trusted because a previous run recorded it.

## stopped_reason

Set once when a budget trips, then read by every other worker to stop taking new
pages.

It is also the "was this run partial" answer the document pipeline needs
afterwards, which is why it is read before the crawler goes out of scope - see
`docs/dev/core/engine.md#stopped_reason`.
