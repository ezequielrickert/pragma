# `spiders/orchestration/mechanical_loop/config.py`

## module

Every tuning knob `MechanicalCrawler` accepts beyond its two core
collaborators (`crawler`, `tracker`) - bundled into one object (mirroring
`Crawl4AICrawlerConfig` in `spiders/browser/crawl4ai_crawler/config.py`,
and the same per-provider `Config` dataclass pattern every agent/
graph-store module uses) instead of a long constructor argument list.

## MechanicalCrawlerConfig

- `fill_value_fn`: How to choose a value for a "fill" (text-input-like)
  component. Defaults to a deterministic placeholder; pass
  `fill_value_agent.make_ai_fill_value_fn(agent)` for a real AI-backed
  one - the only AI call in the crawl loop itself.
- `max_pages`: Overall cap on distinct pages visited, regardless of route
  shape. `None` means unbounded.
- `sink`: Live `GraphStore` writes as the crawl happens. `None` keeps the
  no-persistence default - see `graph_sink/sink.md` for what each call
  actually writes and why it's not folded into `tracker` itself.
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
- `base_url`: Scope boundary for the URL frontier (see
  `frontier.md#enqueue-scope-gate`) - `is_in_scope()` compares hosts
  only. `None` (default) means "use `crawl_site()`'s own start_url" -
  only needed when a caller wants a *different* scope boundary than
  where the crawl happens to start (e.g. starting a few pages deep but
  still scoping to the site root).
- `allow_subdomains`: Passed through to `is_in_scope()` - whether a
  subdomain of `base_url`'s host counts as in-scope.
- `max_requeue_attempts`: see its own section below.
- `session_recycle_after`/`memory_ceiling_percent`/`min_page_concurrency`/
  `concurrency_taper_start_ratio`/`concurrency_taper_end_ratio`: see their
  own sections below.

## max_requeue_attempts

Cap on how many times `UrlFrontier.requeue` will put the same clean_url
key back on the queue after an interrupted pass, before giving up on it
for good (marked `FAILED_PAGE_STATUS` instead -
`docs/dev/spiders/orchestration/graph_sink/sink.md#failed_page_status`).
Confirmed live on austral.edu.ar without a cap: a page whose interactions
reliably trip the anti-bot block, or a popular redirect destination many
different interrupted passes independently requeue, cycled without limit
- "requeued" climbing far past "unique" and the queue growing into the
thousands. Default 3 - generous enough that a genuinely transient block
gets a real second chance, small enough that a page that is *always*
going to fail this way stops burning worker time on it within a handful
of attempts.

## session_recycle_after

How many visits a worker's browser tab carries before `_worker` closes
and rebuilds it. See `loop.md#_recycle_session_if_due` for the measured
cause this exists for. `None` disables recycling entirely (useful for a
crawler fake in a test that doesn't implement `close_session` at all,
or a short crawl where the growth this bounds never gets large enough to
matter). Default 15, picked directly from a live measurement against
austral.edu.ar: recycling every 15 navigations reliably reset JS heap to
single-digit MB and event listeners to double digits each time, well
before either climbed anywhere near the growth that correlated with
multi-second navigation stalls in an unrecycled run.

## memory_ceiling_percent

System-memory-used percent above which a worker pauses picking up its
next page - see `worker_pacing.md#wait_for_memory_headroom`. What makes
raising `page_concurrency` safe rather than just a faster way to
reproduce the same out-of-memory crash: several concurrent Chromium tabs
can genuinely exhaust a machine's memory, and this is the backstop.
`None` disables the check entirely.

## min_page_concurrency

Effective worker count never drops below this even under severe target
strain - see `worker_pacing.md#effective_concurrency`. Default 1: some
progress must always stay possible, regardless of how badly the target
is degraded.

## concurrency_taper

`crawler.target_slowdown_ratio` range over which effective concurrency
linearly tapers from `page_concurrency` down to `min_page_concurrency` -
below `concurrency_taper_start_ratio`, full concurrency; at/above
`concurrency_taper_end_ratio`, the floor. See
`worker_pacing.md#effective_concurrency` for the actual taper math.
