# `spiders/orchestration/graph_sink/tracker.py`

## module

The `InteractionTracker` seam `interaction_tracker.py` already defines,
backed by `GraphStore` reads instead of an in-memory dict, so "have I
already interacted with this" survives across a persisted multi-run
crawl, not just within one process (see
wiki/graph-based-crawl-tracking.md's "the ledger must be consulted, not
write-only"). Its `mark_interacted`/`mark_visited` never perform the
real, detail-rich write - see their sections below - because
`GraphStoreSink` (in `sink.py`) is what actually does that (with
`action`/`value`/`resulting_url` the plain `InteractionTracker` protocol
has no room for); routing a real write through here too would mean
recording every interaction twice, once thin and once rich. They do,
however, update this tracker's own local read cache - a cache update,
not a second store write.

## GraphStoreInteractionTracker

`InteractionTracker` backed by `GraphStore` reads, with a per-instance
local cache.

**Why the cache exists**: `GraphStore.get_component_states` is documented
(see its docstring on `GraphStore`) as "one query per page visit, not one
per component" - but before this cache, `is_interacted` called it fresh
on *every single call*, and `PageVisitor.visit`'s frontier loop calls
`is_interacted` once per component considered, every pass - so a page
with N components did N full `GraphStore` round-trips (a real cost even
for `graph_store: duckdb`'s single-writer-thread hop) just to answer the same "have I
interacted with this yet" question the loop already asked moments ago
for a barely-changed page. This directly contradicted the documented
"one query per page visit" contract rather than merely being slow by
coincidence. `is_visited` had the same shape for `_enqueue`/`_worker`
(called once per discovered link / per dequeue). Caching turns both into
one real `GraphStore` read per page for the lifetime of this tracker
instance (one per `MechanicalCrawler`, i.e. one per crawl) instead of one
per check - a real reduction in `GraphStore` round-trips, and a real
reduction in how often this crawl's own event loop is blocked waiting on
a synchronous backend call (`asyncio.to_thread` to `graph_sink/sink.py`'s
`_write`, for whichever backend is configured).

**Why this is safe** (no interface/behavior change from
`MechanicalCrawler`'s point of view - same sync methods, same signatures,
same semantics): every real write this crawl makes to
"interacted"/"visited" state goes through
`mark_interacted`/`mark_visited`, called at the *same* call sites as the
paired `GraphStoreSink.record_interaction`/`record_page_finished` real
writes - so the cache is updated in lockstep with the real store, for
every write *this* tracker instance's crawl performs. A path never seen
before (new to this page's cache, e.g. a just-revealed component)
correctly falls through to "not interacted" via a plain dict miss -
identical to what a fresh `GraphStore` read would say for a path that was
never written. The only actor that could make this cache stale is a
*different* process/tracker instance writing to the same site
concurrently while this crawl runs - not a new risk this cache
introduces: the existing architecture already assumes
single-writer-per-site-per-crawl (see `PragmaConfig.fresh`/`clear_site`'s
own docstring).

## mark_interacted

Never the real write - `GraphStoreSink.record_interaction` (in
`sink.py`) is what actually calls `GraphStore.record_component_interaction`
for every attempted interaction (success or failure), with the full
`action`/`value`/`resulting_url` detail this protocol method doesn't
carry. Updates this tracker's own local cache only, so a same-pass
re-check of the same path (e.g. the frontier loop revisiting a path
already marked earlier in this same pass) sees it without a redundant
`GraphStore` round-trip - `dict.setdefault` rather than requiring the
path to already be cached, since a component can be marked interacted
(e.g. a failed-interaction path, or one auto-created via
`record_component_interaction`'s own `ON CREATE`) without ever having
gone through `record_component`/being present in an already-cached
page's initial read.

## mark_visited

Never the real write - `GraphStoreSink.record_page_finished` (in
`sink.py`) is what actually calls
`GraphStore.upsert_page(..., status="Finished", ...)` - see that
method's own doc for why it needs the final component count, which this
protocol method doesn't carry. Updates the local cache only, same
reasoning as `mark_interacted` above.
