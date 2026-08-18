# `spiders/browser/crawl4ai_crawler/session_recycle_gate.py`

## module

The third and final piece of a live, three-part austral.edu.ar deadlock
investigation, in order:

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
   every one of these three incidents shared.

This module is the fix: a reader-writer lock, one instance per
`Crawl4AICrawler`, shared by every worker through that one owning
object - not a per-worker lock, since the risk is specifically two
*different* workers' calls racing each other over the *shared* context.

## SessionRecycleGate

See the class's own docstring for the reader/writer roles. Two
`asyncio` primitives, not one: `_condition` (an `asyncio.Condition`)
coordinates the actual reader-count/writer-pending state machine,
`_writer_lock` (a plain `asyncio.Lock`) separately serializes writers
against *each other* - without it, two concurrent `close_session` calls
could each independently see `_writer_pending` already `True` (set by
the other), proceed past their own wait, and one's `finally` block could
clear `_writer_pending` while the other's `kill_session` call was still
running, briefly reopening the gate to new readers mid-recycle. Given
recycling only fires every `session_recycle_after` visits per worker,
contention between two concurrent writers is rare enough that fully
serializing them is a simpler, sufficient answer to that particular
problem than tracking a second reference count.

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
