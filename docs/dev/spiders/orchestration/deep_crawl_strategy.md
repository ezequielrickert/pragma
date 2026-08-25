# spiders/orchestration/deep_crawl_strategy.py

## Module

Part of the map at [issue #231](https://github.com/ezequielrickert/pragma/issues/231)
("Unify pragma's crawl engines around a shared core"). Built to close
[issue #239](https://github.com/ezequielrickert/pragma/issues/239): a
`crawl4ai.deep_crawling.BFSDeepCrawlStrategy` subclass that replaces
`UrlFrontier`/`WorkerPacing`/the hand-rolled worker loop in
`mechanical_loop/loop.py`, per the design locked in
[issue #236](https://github.com/ezequielrickert/pragma/issues/236). Crawl4ai's
own `arun`/`arun_many`/dispatcher drives concurrency; this class only decides,
via `can_process_url`/`link_discovery`, which URLs get a turn.

Not yet wired into any phase command - that's a separate ticket in the same
map (create-and-wire, per the map's Notes). This module and its tests stand
alone against duck-typed `CrawlResult` fakes.

The frontier rules themselves now live in `PragmaFrontierMixin` (below),
extracted per [issue #247](https://github.com/ezequielrickert/pragma/issues/247)
so `spiders/orchestration/best_first_strategy.py`'s `PragmaBestFirstStrategy`
can reuse them without duplicating this module's logic - crawl4ai's
`BFSDeepCrawlStrategy` and `BestFirstCrawlingStrategy` share no common
ancestor below `DeepCrawlStrategy`, so a mixin is the only way to share this
without copying it.

## PragmaFrontierMixin

The route-shape visit cap, `clean_url`-based dedup, and redirect-resolved
identity `UrlFrontier` used to enforce - the part of `PragmaDeepCrawlStrategy`
(below) that isn't BFS-specific, factored out so `PragmaBestFirstStrategy`
carries it too. Mixed in *before* the crawl4ai base class in each
subclass's MRO, so its `super().can_process_url`/`super().link_discovery`
calls reach that base's own implementation.

## PragmaDeepCrawlStrategy

`PragmaFrontierMixin` mixed onto crawl4ai's own
`BFSDeepCrawlStrategy` - unifies the mixin's frontier rules with `CrawlBudget`
exhaustion-stop logic and the hand-rolled worker pool dropped outright, per
#236 - not reintroduced here.

## max_depth

Pragma's own crawl has no depth ceiling - `UrlFrontier` never tracked depth
at all, only route shape and `max_pages`. Both crawl4ai base classes'
`__init__` require a real `int` for `max_depth`, so `sys.maxsize` stands in
for "unbounded."

## _seen

`clean_url()` key already counted as seen. Each crawl4ai base class's own
`visited` set (threaded through `link_discovery`'s parameters) is keyed by
crawl4ai's `normalize_url_for_deep_crawl`, a different canonicalization than
pragma's own dedup identity (scheme/`www.`/fragment/trailing-slash
insensitive - see `utils/urls.py::clean_url`). `_seen` is the pragma-keyed
twin of it, layered on top rather than replacing crawl4ai's own filter.

## can_process_url

Runs crawl4ai's own base check first (URL well-formedness, the filter
chain - `BFSDeepCrawlStrategy`'s and `BestFirstCrawlingStrategy`'s versions
are identical), then pragma's own scope gate (`utils.urls.is_in_scope`) and
route-shape cap. Depth 0 (the crawl's own entry point) bypasses both pragma
gates, matching `UrlFrontier.enqueue(start_url)` never scope-checking the
site's own starting URL against itself.

## prime_route_shape_visits

Ported unchanged from the retired `UrlFrontier.prime_route_shape_visits`:
carries a previous run's already-sampled route shapes into this one, so a
resumed crawl doesn't re-sample a shape a prior run already used up its cap
on. Counts one per already-finished shape - exact at the default
`max_visits_per_route_shape: 1`, an undercount above it (the graph collapses
every literal URL of a shape onto one node, so it can't say whether that
node was reached once or three times).

## _resolved_url

The URL a fetch actually landed on: `redirected_url` when the request was
redirected, `result.url` (the as-requested URL) otherwise. Every dedup/
route-shape decision in this module keys off this, not the as-requested URL,
so two different literal requests that redirect to the same destination
collapse to one - the frontier-level counterpart of the retired
`UrlFrontier.requeue`'s "requeue the resolved URL, not the original request"
fix (the bug confirmed live on empanad.app: re-requesting a redirecting
entry point a second time mints an entirely new session instead of reusing
the one already resolved).

## _mark_seen_and_counted

Record a URL's `clean_url` key as seen and, the first time only, count it
toward its route shape. Returns whether it was already seen. Shared by both
the just-fetched result's own resolved URL and every newly discovered link,
so a redirect target's route shape is counted under its *resolved* identity
even though the link that pointed at it (before the redirect) may carry a
different literal URL and shape.

Counting happens at discovery time, not at completion the way
`UrlFrontier.record_route_shape_visit` did - both crawl4ai base classes
already drain one batch/level of results at a time, calling `link_discovery`
once per completed result in a plain sequential loop (see
`bfs_strategy.py::_arun_batch`, `bff_strategy.py::_arun_best_first`), so
there's no concurrent race between two same-shape links surfacing in the
same batch the way `UrlFrontier`'s worker-pool design had to tolerate.
Counting at discovery is deterministic and enforces the cap without
depending on which of several already-enqueued same-shape candidates
happens to finish fetching first.

## link_discovery

Two things beyond whichever crawl4ai base class's own `link_discovery` this
is mixed onto:

1. Marks the just-completed result's own resolved URL seen/counted (see
   `_resolved_url`/`_mark_seen_and_counted`) - this is what makes a redirect
   target's route shape visible to `can_process_url` for the next candidate
   link of the same shape.
2. Re-filters the newly discovered links (via `_mark_seen_and_counted`) by
   pragma's own `clean_url` identity, on top of whatever crawl4ai's own base
   implementation already queued.

## link_discovery-dedup

`next_level` is shared and accumulated across every result in the current
batch/level - `link_discovery` is called once per completed result, and each
call appends its own newly discovered links onto the same list. Re-deduping
the *whole* list on every call would drop earlier calls' own entries the
moment their key got marked seen by a later call, so this only re-filters
the slice this call itself just appended (`next_level[before:]`), leaving
every prior call's entries untouched.
