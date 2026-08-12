# `src/crawlers/crawl_stopper.py`

## module

Decides whether the current crawl session should end before its frontier
drains, and remembers why.

The point is not to abandon work. A crawl of a large site takes long
enough that the target starts straining against it (see
`target_load_throttle.md`), and long enough that a person wants to stop
for the day. Both were previously all-or-nothing: let it run, or Ctrl-C
and lose the post-crawl synthesis. Stopping deliberately is only useful
because the crawl is *resumable* — everything already visited is in the
graph store, and everything not yet visited is still `Pending` there, so
a stopped session leaves behind exactly the frontier a later session
rehydrates (`resume_state.md`).

Nothing here knows about URLs, browsers or graphs. `MechanicalCrawler`
reports facts to it (a page finished, the target has tripped N times) and
consults it before picking up more work; `Engine` supplies the budgets
and translates a SIGINT into a stop request. Every signal reaching this
module is a plain number or an enum member.

## stopreason

Why a session ended early. Deliberately an `Enum` rather than a string:
the reason reaches the run manifest, `EngineRunResult` and the CLI's
resume hint, and a typo in any of those would silently read as "did not
stop".

The absence of a reason (`None`) is the separate, healthy case — the
frontier drained and the crawl of this site is genuinely complete. That
distinction is what `Engine._should_synthesize` keys off.

- `RATE_LIMITED` — the target kept refusing load; see
  `record_rate_limit_trips`.
- `PAGE_BUDGET` / `TIME_BUDGET` — a deliberate slice, see `sessionbudget`.
- `INTERRUPT` — one Ctrl-C, see `engine.md#_catch_first_interrupt`.

## sessionbudget

How much of a crawl one session may do. Every field is off by default, so
an unbudgeted session behaves exactly as it did before this module
existed — no budget can fire, and `MechanicalCrawler` runs to exhaustion.

### stop_after_pages

Pages this session may visit. **Distinct from `PragmaConfig.max_pages`**,
which bounds the crawl however many sessions it takes: `max_pages` counts
pages already finished by *previous* sessions too (see
`mechanical_loop.md#resume`), while this counts only this sitting.

A soft bound, for the same reason `max_pages` is: with
`page_concurrency` > 1, workers already mid-page when the budget trips are
allowed to finish (`mechanical_loop.md#_wait_for_in_flight_pages`), so the
observed count can exceed the budget by up to `page_concurrency - 1`.
Verified against a local four-page fixture: `stop_after_pages=2` with
`page_concurrency=2` finished 3 pages. Discarding that third page's work
to hit the number exactly would mean re-fetching it next session for
nothing.

### stop_after_seconds

Wall-clock seconds from `begin()`. Enforced by a timer task rather than
by polling, which matters in the case that most needs it: a crawl whose
workers are all parked on a slow target does not evaluate any budget
check for minutes at a time, and a polled deadline would overshoot by
however long the current pages take. The timer fires regardless.

The clock starts at `begin()`, not at construction, so browser-pool
startup does not eat into a session's allowance.

### stop_after_rate_limit_trips

Consecutive circuit-breaker trips that end the session; default 3.

`TargetLoadThrottle` already responds to a straining target by backing
off and pausing every worker, and `MechanicalCrawler` tapers its worker
count on top of that. Those defend the *target*. None of them ever gives
up — against a site that has decided to refuse this crawler, they
converge on hitting it very slowly forever. Past this budget, continuing
is worse than stopping: the frontier is safe on disk either way, and a
resume an hour later starts from a target that is no longer angry.

`None` **or** `0` disables it. Both are accepted because `PragmaConfig`'s
override layer treats `None` as "no value supplied" and falls back to the
default — so `--stop-after-rate-limit-trips 0` is the only way a user can
express "off" through the CLI at all.

## crawlstopper

Owns one session's stop state: an `asyncio.Event`, the first reason, the
session's page count and the deadline task.

### reason

The `StopReason` recorded by the first `request_stop`, or `None`.

### begin

Starts the wall-clock budget, if there is one. Requires a running event
loop (it creates a task). Called once from `crawl_site`, after the
frontier is seeded and immediately before workers start.

Doing nothing when `stop_after_seconds` is unset keeps the common case
free of a task that would only ever be cancelled.

### close

Cancels the deadline task. Safe when `begin` never ran or the deadline
already fired. `crawl_site` calls it in a `finally`, so a crawl that ends
by draining does not leave a timer pending on the loop.

### _stop_at_deadline

Sleeps out the budget, then requests the stop. A plain `asyncio.sleep`
rather than a loop comparing `time.monotonic()`: there is nothing to
re-evaluate, and the loop's own timer is what should be trusted with a
wall-clock deadline.

### request_stop

Ends the session, recording `reason`. Idempotent, and **the first reason
wins**. That ordering is load-bearing rather than arbitrary: a stop is
followed by a grace period during which in-flight pages finish, and those
pages can easily trip a second trigger (a rate-limit trip while
finishing, say). Letting the later trigger overwrite would mean the run
manifest and the operator's console disagree about what actually stopped
the crawl.

Prints one line naming the reason, since by definition nobody asked for
this to happen at this moment.

### should_stop

Whether workers should stop picking up new pages. Checked both before a
worker takes a URL and again after, since a stop can land while the
worker is blocked on the frontier.

### wait

Blocks until something ends the session. `crawl_site` races this against
the frontier draining — see `mechanical_loop.md#_await_drain_or_stop`.

### record_page_visited

Counts one finished page against `stop_after_pages`, tripping the budget
on the page that spends it.

### record_rate_limit_trips

Takes the throttle's current consecutive-trip count and ends the session
once it reaches the budget. Takes the count rather than an increment so
this module owns no duplicate of the throttle's own state — the throttle
decides what a "trip" is and when a streak resets
(`target_load_throttle.md#consecutive_trips`); this decides only how many
in a row are too many.
