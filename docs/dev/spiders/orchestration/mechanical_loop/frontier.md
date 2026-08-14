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
