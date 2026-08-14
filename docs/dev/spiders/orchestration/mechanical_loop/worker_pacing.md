# `spiders/orchestration/mechanical_loop/worker_pacing.py`

## module

How many workers should be actively fetching right now - a memory-
pressure gate plus a target-health-based concurrency taper, independent
of which URLs exist (`frontier.py`) or which worker is currently running
(`loop.py`). Two unrelated reasons a worker might need to hold back
before picking up its next page, kept as one collaborator since both
answer the same underlying question `_worker` asks every loop iteration:
"am I clear to fetch right now?"

## _memory_check_interval_seconds

`wait_for_memory_headroom`'s poll interval while blocked.

## _memory_wait_timeout_seconds

Give up waiting and proceed anyway past this many seconds under the
ceiling, so a machine whose memory pressure has nothing to do with this
crawl (or stays permanently loaded) can't stall it forever.

## _target_health_check_interval_seconds

`wait_for_capacity`'s poll interval while a worker is over budget.

## WorkerPacing

Takes `crawler` and the `MechanicalCrawlerConfig` as constructor
dependencies, and does its own clamping (`page_concurrency`/
`min_page_concurrency` both floored at 1, `min_page_concurrency` never
above `page_concurrency`) rather than trusting `MechanicalCrawler` to
have already done it - a single source of truth for what "valid" means
for these two numbers.

## wait_for_memory_headroom

Block this worker from picking up its next page while system memory is
over `memory_ceiling_percent` used. A crawl with several concurrent
Chromium tabs can genuinely run the machine out of memory; this is what
lets `page_concurrency` be raised without just hitting that ceiling
faster.

## effective_concurrency

How many workers should be actively fetching right now, tapered down
from `page_concurrency` toward `min_page_concurrency` as
`crawler.target_slowdown_ratio` worsens - fewer simultaneous in-flight
requests against a target that's already straining, not just slower
per-request pacing (that's `Crawl4AICrawler`'s own
`TargetLoadThrottle` backoff - see
`docs/dev/spiders/browser/target_load_throttle.md`; this taper is a
second, independent lever on top of it, reducing *concurrency* rather
than *pacing*). Reads a plain attribute `Crawl4AICrawler` updates every
navigation; missing entirely (e.g. a fake crawler in a test) reads as
"healthy", not as degraded, via `getattr(..., 1.0)`.

Below `concurrency_taper_start_ratio`: full `page_concurrency`, no
reduction at all - ordinary page-to-page variance shouldn't cost
throughput. At or above `concurrency_taper_end_ratio`: floors at
`min_page_concurrency` - some progress must always stay possible, even
against a severely straining target. Between the two: linear
interpolation, a gradual response to gradually worsening conditions
rather than an on/off switch.

## wait_for_capacity

Block this worker while its id is outside the currently allowed
concurrency budget (see `effective_concurrency`). `min_page_concurrency`
defaults to 1, so worker 0 always qualifies and the crawl can never
fully stall here - only higher-numbered workers ever wait, and only for
as long as the target stays degraded.
