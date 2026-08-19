# `spiders/browser/crawl4ai_crawler/session_recycle_gate.py`

## module

Part of a live, ongoing austral.edu.ar deadlock investigation, in order:

1. `navigation_watchdog_seconds` (`docs/dev/spiders/browser/crawl4ai_crawler/config.md#navigation_watchdog_seconds`)
   bounded `discover_page()`/`_interact()`'s own `arun()` call.
2. `session_cleanup_timeout_seconds` bounded `close_session()`'s own call
   into `kill_session`.
3. Neither alone explained a *third* freeze, still reproduced after both
   were live: a `py-spy dump` again showed the graph-store writer and
   every thread pool worker completely idle, and by then more than
   5 minutes had passed - well past either individual bound. The
   remaining, best-supported explanation: `close_session`'s own
   `kill_session` call can tear down the *shared* browser context (not
   just the session's own page) if crawl4ai judges it the context's last
   active page - with `page_concurrency > 1`, every worker's session
   shares one context
   (`docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#close_session`,
   point 2), so a recycle racing a concurrent worker's still-in-flight
   navigation could tear the context down out from under it, hanging
   that worker's own `arun()` call indefinitely with no clean error to
   catch - the exact "everything idle, nothing recovering" signature
   every one of these incidents shared. `SessionRecycleGate` was built to
   fix this.
4. Fixed the first three, but a *fourth* freeze still reproduced after
   this module went live too - same signature again (idle writer, idle
   thread pool, minutes of silence). Cause: `SessionRecycleGate`'s own
   first version fully serialized writers against each other through a
   single `asyncio.Lock`, reasoned as safe because recycling is
   infrequent. That reasoning broke down the moment the target started
   straining - the very log evidence this time showed a
   `TargetLoadThrottle` circuit-breaker trip (navigations running 10s+).
   Every worker progresses through pages at roughly the same degraded
   pace, so several independently hit `session_recycle_after` close
   together; each one's own reader-drain wait (already bounded by
   `navigation_watchdog_seconds`) then queued fully behind the last
   instead of running independently, turning an intended ~60s bound into
   up to `page_concurrency` x that - multiple minutes, matching exactly
   what kept reproducing. See `## SessionRecycleGate` below for the fix:
   writers no longer wait on each other, only on readers.

This module is the fix for point 3: a reader-writer lock, one instance
per `Crawl4AICrawler`, shared by every worker through that one owning
object - not a per-worker lock, since the risk is specifically two
*different* workers' calls racing each other over the *shared* context.

## SessionRecycleGate

See the class's own docstring for the reader/writer roles, and for the
full reasoning behind point 4 above: two writers recycling *different*
sessions never conflict with each other in the first place - the one
thing they could actually race on (a shared context's refcount) is
already protected by crawl4ai's own internal lock inside `kill_session`,
not something this gate needs to duplicate. One `asyncio.Condition`
coordinates both roles via two plain counters, `_active_readers` and
`_active_writers` - no separate lock serializing writers against each
other, unlike the version this replaced.

## reader

Entered by `Crawl4AICrawler._run_with_watchdog`, wrapping only the
`arun()` call itself - not the surrounding print/exception handling,
since the reader role exists to represent exactly "the shared browser
resource is currently in use," nothing broader. Releases in a `finally`,
so a watchdog timeout (or any other exception out of the wrapped call)
still frees the slot - a stuck reader must never itself become a second,
new deadlock for any writer waiting on it.

## writer

Entered by `Crawl4AICrawler.close_session`, wrapping only the actual
`kill_session` call, same scoping discipline as `reader`. Takes
`drain_timeout_seconds` as an explicit argument rather than owning its
own constant - `close_session` passes `self.navigation_watchdog_seconds`,
deliberately reusing the exact bound every reader is itself guaranteed
to respect, so a writer's wait for readers to drain can never exceed
what a single hung reader's own recovery already takes. Gives up and
proceeds anyway (with a printed warning) past that deadline rather than
risk a *fourth* deadlock from within the very code meant to prevent the
first three - the same discipline
`docs/dev/spiders/orchestration/mechanical_loop/worker_pacing.md#wait_for_memory_headroom`
already established for its own bounded wait.

Wrapping `asyncio.wait_for(...)` around `Condition.wait_for(...)` is
deliberate, not incidental - `asyncio.Condition.wait()`'s own
implementation re-acquires its underlying lock in a `finally` block
before propagating a `CancelledError`, specifically so a caller wrapping
it in `wait_for` (exactly this usage) is left holding the lock correctly
after a timeout, not in some half-released state. Verified directly
against CPython's own `asyncio/locks.py` before relying on it here.
