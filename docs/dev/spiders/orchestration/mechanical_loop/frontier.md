# `spiders/orchestration/mechanical_loop/frontier.py`

## module

Which URLs are queued, in flight, or already sampled past
`max_visits_per_route_shape` - `MechanicalCrawler`'s site-level URL
frontier, independent of how many workers are draining it or how they're
paced. Split out of `mechanical_loop.py` - this is a plain FIFO queue of
discovered-but-not-visited URLs, fed by every page's extracted links, no
model decision needed, visited in deterministic discovery order. The
*component/interaction* frontier is a different, per-page concept owned
by `PageVisitor` (`docs/dev/spiders/orchestration/page_visitor/frontier.md`)
- the two are composed but never conflated.

## UrlFrontier

Owns the queue plus the dedup/in-flight/route-shape-visit bookkeeping
around it. `MechanicalCrawler.__init__` constructs one instance and reads
`base_url` off it in `crawl_site`; `PageVisitor` never touches this class
directly, only the `enqueue`/`enqueue_links` bound methods passed to it
as plain callables.

## _queue

`asyncio.Queue`, not a plain deque: `crawl_site`'s worker(s) need to
`await` for a new item rather than busy-poll, and `.join()` is what lets
`crawl_site` know every enqueued item (including ones enqueued *during*
another item's processing) has been fully handled, with no separate "is
anything still in flight" bookkeeping of its own.

## _pending

clean_url keys currently sitting un-popped in `_queue` right now - unlike
`_queued` (permanent, set once, never shrinks), this one drains on `get()`.
Exists so `requeue()` can tell "this destination already has a live entry
waiting" apart from "needs a fresh one" - the fact `_queued` alone can't
answer, since it stays `True` forever once anything is ever enqueued,
whether or not it's still actually sitting in the queue.

Always a subset of `_queued`: every key added to `_pending` (by `enqueue()`
or `requeue()`) was already added to `_queued` at that same moment or
earlier, and nothing ever removes a key from `_queued`. That's why
`is_known()` doesn't need a separate `_pending` check of its own.

## in_flight

clean_url keys a worker is *currently* mid-visit on - a second, narrower
guard than the enqueue dedup set, needed specifically because the
interrupted-navigation follow-up requeue (see
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker`)
deliberately bypasses `enqueue`'s own dedup (it has to: the page it's
resuming is, by definition, already in that set). That bypass has no way
to know whether some *other*, unrelated page redirected to the exact
same destination and already requeued it too - confirmed live on a real
crawl (mapadeprofesionales.com, `page_concurrency=10`): many distinct
pages' own "log in" links all redirect to the identical `/login` URL,
each interrupted pass independently calls `requeue()` for it, and two
idle workers ended up running `PageVisitor.visit()` for the identical
clean_url/session_id at the same time - a real race on the same live
crawl4ai browser session (crawl4ai keys its own session cache by this
exact string), not just a debug-log cosmetic issue: the *visible* symptom
was the debug_log page-markdown snapshot being overwritten mid-flight by
whichever worker's write landed second, silently losing the other's.

## enqueue

The single choke point every discovered URL passes through (a plain
link, a follow-up-pass requeue via `requeue()` aside, or a real
navigation's destination all call this), so this one check covers every
way the crawl could otherwise wander off-site: a link to an external
domain, or a click/redirect that lands there (see
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation`,
which calls this with `new_state.url` - an out-of-scope destination
there is still correctly recorded as a navigation edge, just never
itself visited/crawled further).

## enqueue-scope-gate

`self.base_url` is set by `MechanicalCrawler.crawl_site()` before its own
first `enqueue()` call if not given explicitly via
`MechanicalCrawlerConfig.base_url`.

## enqueue_links

Queue every http(s) href onto the URL frontier - shared by both the
initial-discovery call site and every same-page-reveal call site in
`PageVisitor`, so a link that only exists inside a revealed dropdown/menu
gets queued exactly like one present on initial load. Safe to call
repeatedly for the same links - `enqueue`'s own dedup guard makes this
idempotent.

## enqueue_scouted

Re-add a URL phase 1 of a `two_phase_crawl` run
(`config.md#two_phase_crawl`) already fully drained through this same
frontier's `_queued` dedup set. A plain `enqueue()` call would silently
refuse it - the whole point of `_queued` is "never queue the same key
twice" - so phase 2 needs its own entry point past that one guard, while
still keeping the scope gate (`enqueue-scope-gate` above).

Deliberately doesn't touch `_requeue_attempts` or `_route_shape_visits`,
unlike `requeue()` just below: this isn't a failure retry, and the
scouted set already respects `max_visits_per_route_shape` from phase 1's
own `enqueue()` gate the first time each URL went through it.

## requeue

Put a URL straight onto the queue, bypassing every gate `enqueue` applies
- used exactly once, by `_worker`'s interrupted-navigation follow-up (see
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-requeue`),
which needs to resume a page already known to be in-scope and already
past its route-shape/dedup checks the first time it was enqueued.

Short-circuits to `True` - without touching `_requeue_attempts` - if the
key is already `_pending` (a live entry is still sitting un-popped in the
queue) or `_in_flight` (a worker is visiting it right now). Confirmed live
on a real crawl (austral.edu.ar): a popular redirect destination many
different interrupted passes independently call this for (the exact race
`in_flight`'s own doc describes) used to succeed every single time,
putting the same clean_url key in `_queue` more than once - not a
double-*visit* (the dequeue-time `is_visited`/`is_in_flight` checks in
`loop.md#_worker` already caught that), but dead entries that inflated
`queued_count()`, cost a full pacing-wait/dequeue/check cycle for nothing,
and let `_requeue_attempts` climb from duplicate bookkeeping alone. A
short-circuited call isn't a real retry - nothing new happened - so it's
deliberately not counted as one; only a call that actually puts a fresh
entry on the queue advances the counter.

Otherwise returns `False` instead of requeuing once `max_requeue_attempts`
is exceeded for that clean_url key - see `_requeue_attempts` below. A page
that reliably trips an anti-bot block still has this real backstop; it's
only the *duplicate-call* version of unbounded growth that the
short-circuit above removes.

## is_known

Whether `url`'s clean_url key is already in `_queued` (queued or already
dequeued - `_queued` is a dedup guard, never pruned), currently
`in_flight`, or `tracker.is_visited` - i.e. whether this crawl already has
a place for it, without regard for *how* it got there.

Read by
`docs/dev/spiders/orchestration/page_visitor/outcomes.md#handle_physical_navigation`
before deciding whether a mid-pass navigation is worth pausing the whole
page for: a link to a destination already covered by one of these three
doesn't need a separate pass of its own, so
`docs/dev/spiders/orchestration/page_visitor/recovery.md#return_to_origin`
can hop the browser back and keep going instead.

Deliberately checks `tracker.is_visited` too, not just `_queued` - a page
finished in a *previous* run (resumed via `MechanicalCrawler._resume_urls`)
is never re-added to `_queued` this run (only still-Pending URLs are), but
is exactly as "already accounted for" as one this run queued itself.

## _requeue_attempts

clean_url key -> how many times `requeue` has actually put a fresh entry
on the queue for it - a call absorbed by the `_pending`/`_in_flight`
short-circuit above doesn't advance this. Keyed by the destination, not by
which pass called it or which worker is running - the whole point is to
cap a popular destination's *total* real requeue count across every
independent interrupted pass that lands on it, not just one page's own
retry count.

`_worker`'s caller reads `requeue`'s return value to know when to stop:
past the cap, it marks the page `FAILED_PAGE_STATUS`
(`docs/dev/spiders/orchestration/graph_sink/sink.md#failed_page_status`)
instead of calling this again.

## queued_count

How many URLs are still waiting - the denominator a progress line needs to
distinguish "working through a long list" from "stuck".

## prime_route_shape_visits

Carries a previous run's sampled route shapes into this one.

Without it the counter starts at zero every run, so `max_visits_per_route_shape`
was per-*run* rather than per-*site*: five short runs sampled up to five URLs of
a shape where one long run sampled one, and **the same site crawled two
different ways produced two different graphs**. Making short runs equivalent to
one long run is the whole point of the resume path, and this was the piece of
state silently breaking it.
