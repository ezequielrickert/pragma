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
- `scout_only`/`interact_only`: see their own sections below.

## scout_only

When `True`, `crawl_site()` runs the scout sweep alone and returns - no
interact phase, in this process or any later one triggered by it. Pages
land in the graph store `"Scouted"`, so a later, separate `pragma
dynamic` invocation can pick them up via `get_scouted()`. This is
`pragma static`'s own crawl mode (`core/static_engine.py::StaticEngine`).

Motivated by a user request to scout a site cheaply first (full
component/link/text extraction, zero clicking) before committing to the
expensive click/fill interaction pass. crawl4ai's own `prefetch` flag
(`spiders/browser/crawl4ai_crawler/config.md`) looked like the obvious
lever but turned out to be a dead end for this: verified against the
installed package, `prefetch=True` only skips crawl4ai's own
markdown-generation pipeline - this project's actual component/link/text
extraction runs earlier, in `before_retrieve_html`/`on_execution_ended`
(`docs/dev/spiders/browser/crawl4ai_crawler/hooks.md`), unaffected by
that flag either way. `discover_page()` was already exactly the cheap
scout fetch wanted; it just wasn't exposed as its own mode. Not named
`prefetch` itself - that name is already `Crawl4AICrawlerConfig.prefetch`,
the unrelated flag discussed above, and reusing it here for a wholly
different mechanism would be actively misleading.

## interact_only

When `True`, `crawl_site()` skips discovery entirely: `start_url` is
never enqueued, and the frontier is seeded only from whatever a
previous, separate `scout_only` run already left `"Scouted"`
(`get_scouted()`) - then a single interact sweep runs over exactly that.
This is `pragma dynamic`'s own resume mode
(`core/dynamic_engine.py::DynamicEngine`) when a prior `pragma static`
run exists for the site; `DynamicEngine` falls back to leaving this
`False` (the ordinary fused `visit()` pass) when it doesn't.

`interact()` still has to call `discover_page()` a second time - the
browser tab necessarily moved off every page since the earlier
`scout_only` run, and per
`docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities`
a component's own path/selector churns across separate `discover_page()`
reloads, so a `scout()`-cached component can't drive a live click here.
The real saving `interact()` captures instead: it skips the six sink
bookkeeping writes (`record_page_arrival`/`record_inventory`/
`record_text_content`/`record_state_styles`/`record_page_network`/
`record_page_metadata` - the last of which does real work, component-
family/choice-set grouping) and the `enqueue_links` walk, since
`scout()` already did both for every page `interact()` runs against.

Known, accepted limitation: an `interact_only=True` run interrupted
mid-sweep does not resume cleanly today - `loop.md#_resume_urls`/
`_finished_route_shapes` only read `Pending`/`Finished` status, so a
resumed run won't re-prime route-shape counts for `Scouted`-but-not-yet-
interacted pages, and has no "pick up where interact_only left off" path
of its own.

## family_sampler

`analysis/family_sampling.py::FamilySampler`, or `None` to interact with
every eligible component as usual. Consulted by `PageVisitor` once per
component, before any click/fill - the mechanism `pragma dynamic` uses
to skip components already known (via `pragma cluster`'s output) to
belong to a repeating family once enough instances of that family have
already been sampled. `None` for every caller except `DynamicEngine`,
which only builds one when `graph_store.get_component_families()` isn't
empty - see `docs/dev/core/dynamic_engine.md#_build_family_sampler`.

## max_requeue_attempts

Cap on how many times `UrlFrontier.requeue` will put the same clean_url
key back on the queue after an interrupted pass, before giving up on it
for good (marked `FAILED_PAGE_STATUS` instead -
`docs/dev/spiders/orchestration/graph_sink/sink.md#failed_page_status`).
Confirmed live on austral.edu.ar without this cap: a page whose
interactions reliably trip the anti-bot block cycled without limit.
Default 3 - generous enough that a genuinely transient block gets a real
second chance, small enough that a page that is *always* going to fail
this way stops burning worker time on it within a handful of attempts.

A *separate* bug, also found on austral.edu.ar and now fixed independently
of this cap (`frontier.md#_pending`), used to let a popular redirect
destination many different interrupted passes independently requeue
duplicate itself into the live queue - "requeued" climbing far past
"unique" and the queue growing into the thousands purely from dead
duplicate entries, not from this cap being too high. `requeue()` now
short-circuits a call for a URL that's already pending or in flight
instead of queuing a second copy, and that short-circuited call doesn't
consume one of this cap's attempts either - only a call that actually
needs a fresh entry does.

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

## budget

What this run is allowed to do before stopping and leaving the rest `Pending`.

All-unset (the default) means "until the frontier drains", which is what every
run did before budgets existed. See
`docs/dev/spiders/orchestration/mechanical_loop/budget.md`.
