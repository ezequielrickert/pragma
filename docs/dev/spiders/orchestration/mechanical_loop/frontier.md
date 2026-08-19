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

## requeue

Put a URL straight onto the queue, bypassing every gate `enqueue` applies
- used exactly once, by `_worker`'s interrupted-navigation follow-up (see
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-requeue`),
which needs to resume a page already known to be in-scope and already
past its route-shape/dedup checks the first time it was enqueued.

Returns `False` instead of requeuing once `max_requeue_attempts` is
exceeded for that clean_url key - see `_requeue_attempts` below. Confirmed
live on a real crawl (austral.edu.ar): a reliably anti-bot-blocked page,
or a popular redirect destination many different interrupted passes
independently call this for (the exact race `in_flight`'s own doc
describes), had no limit before this - "requeued" climbed far past
"unique" and the queue grew into the thousands on a site with a few
hundred real pages, because every interrupted pass added its own copy
with nothing capping how many times any one destination could cycle back
through.

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

clean_url key -> how many times `requeue` has been called for it. Keyed
by the destination, not by which pass called it or which worker is
running - the whole point is to cap a popular destination's *total*
requeue count across every independent interrupted pass that lands on
it, not just one page's own retry count.

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
