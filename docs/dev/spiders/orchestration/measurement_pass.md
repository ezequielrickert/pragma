# `spiders/orchestration/measurement_pass.py`

## module

Re-visit an already-crawled site with a browser configured to represent a
user rather than to be fast.

**Why a second pass rather than fixing the crawl.** The crawl's browser
runs at 800x600 with `light_mode`, `memory_saving_mode`, and images, media
and fonts blocked. Every one of those is a deliberate speed decision, and
together they make anything measured through it unrepresentative -
contrast in particular, since a background that comes from an image simply
is not there. Making the crawl faithful would slow the part of the
pipeline that already dominates wall-clock time, to serve documents that
are a fraction of the value.

**Why it is cheap.** It only navigates. No clicking, no filling, no
frontier, no re-discovery - which is what makes it a fraction of the crawl
rather than a second one. The crawl spends its time on interactions.

## measurementresult

Reports what it could not reach as well as what it did, because the gap is
not obvious from the outside - see `_navigable`.

## _navigable

Page nodes are keyed by `route_shape`, so a page whose path held an opaque
token is stored as `example.com/o/{token}` - a shape, not an address. The
literal URL is not persisted anywhere, so those pages cannot be re-visited
at all.

They are reported in `skipped_shaped_routes` rather than quietly dropped.
The fix, when it matters, is to persist the literal URL alongside the
shape on the Page node; it was not worth doing before knowing whether the
audit was useful.

## run_measurement_pass

Visits every **finished** page. That is already the sampled pass rather
than an exhaustive one: `max_visits_per_route_shape` means the crawl only
ever recorded one page node per route shape, so there is nothing left to
sample.

A page that fails to load is skipped with a warning rather than aborting
the pass. This is an enhancement on top of a finished crawl, and losing
all of it because one page 500s would be a poor trade.

Navigation itself goes through `Crawl4AICrawler.discover_pages_many` (a
single `arun_many()`/`MemoryAdaptiveDispatcher` batch call) instead of a
hand-rolled `for page_url in navigable:` loop that used to call
`discover_page` once per page. This pass's shape - many independent,
already-known URLs, no interaction, no session reused between pages - is
exactly what `arun_many()` is built for, unlike the main crawl's own
click/fill loop (see
`docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#discover_pages_many` for why
that one keeps its own throttle instead). A `None` `PageState` in the
returned list is this pass's "skipped with a warning" page, same
contract as before.
