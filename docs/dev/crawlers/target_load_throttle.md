# `src/crawlers/target_load_throttle.py`

## module

Adaptive pacing against a target server that is straining under load.

One instance is shared by the whole crawl — `Crawl4AICrawlerPool` builds
it and hands the same object to every pool member, because there is one
target server and therefore one load signal. `Crawl4AICrawler` consults
it before every navigation and reports back after.

This module only tracks and reports facts about the target. It has no
idea that workers or concurrency exist; `MechanicalCrawler` reads
`target_slowdown_ratio` off the crawler and tapers its own worker count
(`mechanical_loop.md#_effective_concurrency`), and `CrawlStopper` reads
`consecutive_trips` to decide whether to end the session
(`crawl_stopper.md#stop_after_rate_limit_trips`). Neither decision
belongs here.

## _backoff_slowdown_multiplier

A navigation this many times slower than the fastest one seen this crawl
counts as the target straining, rather than ordinary page-to-page
variance. Below it, backoff decays.

## _backoff_proportional_factor

Backoff grows toward `elapsed_seconds * this` on a slowdown and decays by
this same fraction of itself on a fast navigation.

Proportional, not a fixed step: a single 1s navigation should provoke far
more caution than a single 6s one, which a fixed step cannot express. The
fixed-step version was live-tested against a real degrading target and
proved too weak — see `record_navigation` below.

## _severe_slowdown_multiplier

The point at which a slowdown trips the circuit breaker, pausing *every*
worker rather than merely slowing each one. By here the target is
straining badly enough that adding load is more likely to make things
worse than to finish sooner.

## _rate_limit_status_codes

`429` and `503` — statuses in which the target says outright that it is
being asked for too much.

Every other signal in this module is inferred from latency, and latency
misses this case badly. A 429 is typically served from an edge cache in a
few tens of milliseconds: not only does it fail to read as a slowdown, it
reads as the *fastest* navigation of the crawl so far. See
`record_navigation`.

## targetloadthrottle

### _backoff_seconds

Current per-navigation delay, shared across every worker.

### _circuit_breaker_until

A `time.monotonic()` deadline, not the event loop's clock —
`record_navigation` is a plain sync method, callable with no loop
running. `0.0` means never tripped. Every worker's own
`wait_before_navigation` blocks until it passes, so one trip pauses the
whole crawl.

### target_slowdown_ratio

How many times slower the most recent navigation was than the fastest one
seen this crawl. `1.0` = no observed slowdown. Always updated, even when
backoff is disabled, because `_effective_concurrency` reads it
independently of whether backoff and the circuit breaker are on.

### consecutive_trips

Circuit-breaker trips since the last healthy navigation.

One trip on its own is ordinary and means the mechanism worked: the crawl
paused, the target recovered, work continued. What matters is trips that
keep stacking with no healthy navigation between them — that is the
target telling the crawler the pauses are not achieving anything, which
is the signal `CrawlStopper` acts on.

Reset in the healthy branch of `record_navigation` (a navigation back
within `_BACKOFF_SLOWDOWN_MULTIPLIER` of the floor), and incremented in
`_trip_circuit_breaker` only when a trip actually extends the deadline —
so a burst of trips inside one cooldown counts once, not once per worker
that noticed.

### wait_before_navigation

Pauses for the circuit breaker's remaining cooldown if tripped, otherwise
sleeps off the current backoff. Every worker calls it before its own
navigation, which is what makes a tripped breaker pause the entire crawl
rather than one worker.

### record_navigation

Reports one completed navigation. Two paths.

**With a rate-limiting `status_code`**, everything else is skipped: the
breaker trips immediately (unless backoff is disabled entirely, which
already means "no circuit breaker" and must not be re-enabled through a
side door), and **the timing is deliberately not recorded**. Letting a
0.05s 429 set `_fastest_navigation_seconds` would poison the baseline for
the rest of the crawl — every genuine page afterwards would measure as a
40x slowdown against it, and the crawl would throttle itself to a halt
over a target that had recovered.

**Otherwise** the latency signal governs, as it always did:

- within `_BACKOFF_SLOWDOWN_MULTIPLIER`x the floor: decay backoff, and
  reset the trip streak.
- beyond it: grow backoff toward this navigation's own elapsed time.
- beyond `_SEVERE_SLOWDOWN_MULTIPLIER`x: also trip the circuit breaker.

#### record_navigation-live-evidence

The proportional design was confirmed against a real degrading target
(austral.edu.ar): across one continuous ~530-request crawl, FETCH times
climbed from ~2.6s average to ~14.3s average, peaking past 37s. A fixed
step regardless of severity did not keep up with that curve.

### _trip_circuit_breaker

Pauses every worker's next navigation for
`circuit_breaker_cooldown_seconds`, and counts the trip. Returns early
without counting when the breaker is already tripped further out than
this would extend it — several workers each discovering the same
straining target within one cooldown is one event, not several.
