# `spiders/browser/target_load_throttle.py`

## module

Adaptive pacing/circuit-breaker against a target server that's straining
under this crawl's own request load. Split out of `crawl4ai_crawler.py`
as its own small class - it tracks/reports facts about the target only,
with no idea workers or concurrency exist - `Crawl4AICrawler` owns one
instance and consults it before/after every navigation, while
`MechanicalCrawler` separately reads `target_slowdown_ratio` off the
crawler to taper its own worker count (see
`docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#_effective_concurrency`).

Superseded an earlier design (a bare `_backoff_seconds` float plus
`_throttle_for_target_load`/`_update_backoff` methods living directly on
`Crawl4AICrawler`) with the same AIMD (additive-increase/additive-decrease)
shape but a proportional, not fixed-step, growth rule - see
`record_navigation` below for why the fixed step proved too weak.

**Why this exists at all**, confirmed by bypassing this entire class -
raw `urllib` GETs, no Playwright, no browser - against 86 distinct real
`austral.edu.ar` URLs, reading the site's own `X-Cache` response header:
requests the header marked `TCP_HIT`/`TCP_REMOTE_HIT` (served from the
site's own cache) stayed under ~1s for the *entire* run, no matter how
late; requests marked `TCP_MISS` (the site's cache had to hit its own
origin/backend) started around 1-2s early in the run and were regularly
6-10s+ by request 40-85, with zero browser involvement anywhere in this
measurement. That rules out everything client-side this project owns
(JS heap, event listeners, crawl4ai's session/context bookkeeping, this
project's own Python state) as the cause of a real crawl's `[FETCH]`
timing climbing over a long run - it's the *target's own backend*
degrading under this crawl's sustained request rate, something no
client-side fix can touch, since the plain-HTTP measurement showed the
identical pattern with none of that machinery even running.

## _backoff_slowdown_multiplier

How many times slower than the fastest navigation seen this crawl counts
as the *target server* straining rather than ordinary page-to-page
variance (heavier pages are always somewhat slower than light ones, on
any healthy server). 2.0 is deliberately generous - see `record_navigation`
for why a tighter multiplier would misfire on normal variance.

## _backoff_proportional_factor

Backoff grows toward `elapsed_seconds * this factor` on a slowdown, and
decays by this same fraction of itself on a fast navigation -
proportional, not a fixed step. A single 1s-over-floor navigation should
provoke far less caution than a single 6s one, not the same fixed nudge
either would under a fixed-step design - see `record_navigation-live-evidence`
below for why a fixed step proved too weak in practice.

## record_navigation-live-evidence

The earlier fixed-step design's backoff grew far more slowly than
`austral.edu.ar`'s own real FETCH-time climb: ~2.6s avg to ~14.3s avg,
peaking past 37s, across one continuous ~530-request crawl. By the time
a fixed step had accumulated enough caution, the target had already
degraded much further. A proportional step tracks the *magnitude* of
each slowdown directly instead of learning it one small increment at a
time.

## _severe_slowdown_multiplier

A navigation this many times slower than the fastest one seen this crawl
trips the circuit breaker - pausing every worker, not just slowing them
down, since by this point the target is straining badly enough that
continuing to add load is more likely to make it worse than to finish
faster.

## TargetLoadThrottle

`Crawl4AICrawler` owns one instance and consults it before/after every
navigation; `MechanicalCrawler` reads `target_slowdown_ratio` off the
crawler to taper its own worker count - this class only tracks/reports
facts about the target, it has no idea workers or concurrency exist.

## _backoff_seconds

Shared across every worker that shares this instance - one target
server, one load signal, regardless of how many concurrent sessions
(or, before the multi-process pool was removed, how many separate
browser processes) are watching it.

## _circuit_breaker_until

A `time.monotonic()` deadline, not the event loop's own clock -
`record_navigation` is a plain sync method, callable with no loop
running. Every worker's own `wait_before_navigation` call blocks until
this passes, once tripped. `0.0` means never tripped.

## target_slowdown_ratio

Public fact about the target; `1.0` means no observed slowdown. Always
updated by `record_navigation`, even with backoff disabled entirely
(`backoff_ceiling_seconds=None`) - `MechanicalCrawler`'s own concurrency
taper reads this independently of whether backoff/circuit-breaker are on.

## wait_before_navigation

Pause for the circuit breaker's remaining cooldown if tripped, otherwise
sleep off the crawl's current backoff, before issuing a navigation.
Every worker calls this before its own navigation, so a tripped circuit
breaker pauses the whole crawl, not just one worker.

## record_navigation

Tracks how this navigation compares to the fastest seen this crawl (a
floor, not an average - one fast sample is proof the target *can*
respond that fast, so a single early lucky low sample is a legitimate
reference point, not noise), and reacts proportionally to how bad it
was:

- within `_backoff_slowdown_multiplier`x the floor: decay backoff.
- beyond it: grow backoff toward this navigation's own elapsed time (see
  `_backoff_proportional_factor` above for why proportional, not fixed-step).
- beyond `_severe_slowdown_multiplier`x: also trip the circuit breaker.

Deliberately only ever called from `discover_page`, not `_interact` (the
shared `click`/`fill`/`resync` implementation): a `js_only=True`
interaction call almost never re-fetches the origin at all (it
manipulates the already-loaded DOM in place), so its timing reflects
local browser/JS cost, not target-server load - mixing the two into one
signal would corrupt the "fastest seen" floor with numbers an order of
magnitude smaller than a real navigation, making ordinary navigations
look like a slowdown on every single one.

`backoff_ceiling_seconds=None` skips backoff/circuit-breaker tracking
entirely (though `target_slowdown_ratio` is still updated - see that
section above) - a caller that never wants backoff pays nothing for it.

## _trip_circuit_breaker

Pause every worker's next navigation for `circuit_breaker_cooldown_seconds`.
Idempotent against an already-further-out trip: a second severe slowdown
while already tripped extends the cooldown only if it would push the
deadline later, never pulls it earlier.
