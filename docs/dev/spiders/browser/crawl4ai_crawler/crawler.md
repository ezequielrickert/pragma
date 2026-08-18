# `spiders/browser/crawl4ai_crawler/crawler.py`

## module

crawl4ai-backed page discovery (Phase 1 of the crawl4ai migration - see
`wiki/` for background).

This module proves and exposes exactly one thing: that
`PlaywrightScraper._discover_components`'s battle-tested discovery JS
(unique selectors, full ARIA-role coverage, shadow-DOM piercing,
accessible-label fallback chain, per-frame discovery) runs unmodified
inside a crawl4ai hook, driven by a real `AsyncWebCrawler`/`Playwright`
page instead of Pragma's old sync, lazily-started single `Page`.
`discover_page()` is the primary entry point: navigate to a URL, run
every read-only extraction pass, return a `PageState`. `click()`/`fill()`/
`resync()` drive the mechanical interaction loop against an existing
session instead.

This class owns the browser and the navigate/interact API surface only;
the crawl4ai hook callbacks themselves and the `PageState`-assembly logic
are their own collaborators - see
`docs/dev/spiders/browser/crawl4ai_crawler/hooks.md` and
`docs/dev/spiders/browser/crawl4ai_crawler/page_state.md`.

## Crawl4AICrawler

Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with`
block - matching crawl4ai's own browser-lifecycle model (start once, run
many `arun()` calls, close once) rather than Pragma's old per-action
lazy-start model. Use as:

```python
async with Crawl4AICrawler() as crawler:
    state = await crawler.discover_page(url)
```

## __aenter__-browserconfig

`light_mode`/`memory_saving_mode` disable background browser features
(not layout/CSS - unlike `text_mode`, which this project deliberately
never sets, since `discover_components.js` needs real computed styles
and layout for its pointer-cursor/visibility detection) and a smaller
viewport cuts render cost per navigation.

## __aenter__-hook-order

Hooks must be registered *before* `__aenter__()` is awaited below -
confirmed by reading crawl4ai's own source: `on_browser_created` fires
from inside `crawler_strategy.start()`, which `AsyncWebCrawler.__aenter__()`
calls immediately. Registering after `__aenter__()` (this module's
original order) means that specific hook's callback is set too late to
ever see its own firing.

## __aenter__-single-slot-hooks

`on_page_context_created` is always registered (not gated on
`debug_log`) - it's where `block_images`'s route handler gets installed
regardless of debug logging; the handler itself folds in the log-only
behavior when `debug_log` is set, since crawl4ai only allows one
callback per hook name (confirmed: `self.hooks` is a single-slot dict
per hook type, not a list) - registering a second handler here would
silently replace, not add to, this one. See
`docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_page_context_created`.

## __aenter__-quiet-logger

`AsyncWebCrawler` gets a `QuietCaptureLogger`
(`docs/dev/spiders/browser/crawl4ai_crawler/quiet_logger.md`) instead of
letting it build its own default `AsyncLogger` - built with
`verbose=browser_config.verbose` to match exactly what the default
construction would have used, so this changes nothing except dropping one
specific noisy tag.

## discover_page

Navigate to `url` and return its `PageState` - components, links,
description, metadata, all via read-only extraction. No interaction.

`session_id` defaults to `url` when the caller doesn't pass one, so a
call made in isolation never races another on the hooks' shared stash
key. `MechanicalCrawler` passes its own explicit `session_id` instead -
one stable value per worker, reused across every URL that worker visits
in turn - so a whole crawl reuses `page_concurrency` browser tabs rather
than opening a new one per page. See
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker` and
`docs/dev/spiders/orchestration/page_visitor/visitor.md#visit`.

## discover_page-network-capture

A page's own load fires the API calls a SPA needs to render at all - not
attributable to any one component, but part of the contract all the
same.

The `arun()` call itself goes through `_run_with_watchdog`, not a bare
`await self._crawler.arun(...)` - see that section below for why
`page_timeout_seconds` alone isn't a sufficient bound.

## _run_with_watchdog

Wraps `self._crawler.arun(...)` in `asyncio.wait_for(...,
timeout=navigation_watchdog_seconds)` - an outer backstop independent of
`page_timeout_seconds`, which only bounds crawl4ai's own internal
navigation clock once a navigation has actually started. See
`docs/dev/spiders/browser/crawl4ai_crawler/config.md#navigation_watchdog_seconds`
for the live austral.edu.ar deadlock this exists for and the reasoning
behind the default. Shared by `discover_page()` and `_interact()` - both
go through the identical `arun()` call, and both are equally exposed to
whatever this guards against (a real crawl4ai/Playwright hang doesn't
care whether it's mid-navigation or mid-interaction).

Prints `[arun] {session_id} -> {url}` before the call - crawl4ai's own
`[FETCH]`/`[SCRAPE]`/`[COMPLETE]` console lines only print *after* each
phase finishes (they carry a timing), so a genuine hang otherwise leaves
no trace of which URL a worker was even attempting. Confirmed live: a
12+ minute deadlock left nothing in the console or `debug.md` to
distinguish "which page" a frozen worker was on.

On timeout, calls `_force_close_wedged_session` before re-raising as a
`RuntimeError` - `PageVisitor._discover_or_fail` (or `_interact`'s own
callers) already know how to turn any `RuntimeError` from this layer
into an ordinary, recoverable per-page failure instead of propagating
and killing the worker.

## _force_close_wedged_session

Best-effort session cleanup after a watchdog timeout - tries
`close_session(session_id)` so this worker's *next* call gets a fresh
session instead of possibly inheriting whatever internal crawl4ai state
caused this one to wedge. Bounded by its own short, separate timeout
(`_WEDGED_SESSION_CLEANUP_TIMEOUT_SECONDS`, 10s) and any exception is
caught and only printed - a cleanup attempt that's itself stuck on the
same underlying problem must never mask the original watchdog error or
introduce a second unbounded wait on top of the first.

**Explicitly a partial fix, stated plainly rather than oversold**: this
codebase doesn't control crawl4ai's own internals, so neither this nor
the watchdog above can fix whatever actually wedged inside it - they can
only stop *this codebase's own loop* from hanging forever because of it,
converting an unbounded, silent freeze into a bounded, recoverable,
per-page failure. If the true root cause turns out to be a leaked lock
inside crawl4ai's own session/browser-management code, closing the
session is the most this layer can do about it from the outside.

## _save_markdown

Save crawl4ai's own readable-markdown conversion of the page `result`
just captured, if debug logging is enabled. Best-effort: `result.markdown`
can legitimately be `None`/absent depending on crawl4ai's config, and a
failure here must never break the crawl itself over what's purely a
debugging convenience.

Keyed by `url` - the literal address this specific call was requested
with - deliberately NOT `session_id` and NOT the post-redirect
`page_state.url`.

Not `page_state.url`: an earlier version of this method used it, and on
a real crawl (mapadeprofesionales.com, `page_concurrency=10`) many
distinct pages' own "log in" links all redirect to the identical
resolved `/login` URL; keying by that resolved destination meant every
one of those sessions' markdown snapshots landed on the exact same
filename, so whichever one saved last silently overwrote every other
one's content - losing real information, not just a naming collision.
See `docs/dev/spiders/orchestration/mechanical_loop/frontier.md#in_flight`
for the deeper fix (preventing two of those sessions from ever running
concurrently in the first place) - this key change is a second,
independent layer: even a legitimate, non-concurrent, sequential resume
of the *same* session correctly keeps overwriting its own file (the
intended "live snapshot" behavior), while two genuinely *different*
sessions that happen to redirect to the same destination now keep their
own separate, inspectable files instead of one clobbering the other.

Not `session_id` either, now that `session_id` names a *reused browser
tab* rather than a page: since `MechanicalCrawler` hands every worker's
whole run of URLs the same `session_id` (see `#discover_page` above),
using it here would collapse every page one worker ever visits onto a
single markdown filename. `url` is the one identifier that's still
one-per-page regardless of how many pages end up sharing a tab.

## _interact

Run `js_code` against the existing `session_id` session (no full
navigation - `js_only=True`) and return the resulting `PageState`,
re-discovered via `on_execution_ended`
(`docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_execution_ended`).

A real action failure (element not found, a raised JS exception)
propagates as a `RuntimeError` - the primary action must never look like
a successful no-op, per wiki/browser-automation-pitfalls.md. `session_id`
must be the same one `discover_page()` was called with for this URL, so
this reuses the live page/session instead of triggering a fresh
navigation.

Its own `arun()` call goes through `_run_with_watchdog` too, same as
`discover_page()`'s - a hang here (mid-click, mid-fill) is exactly as
possible as one during navigation, and exactly as invisible to
`page_timeout_seconds` alone.

## _interact-network-capture

Network capture is only enabled here, not in `discover_page()`'s plain
navigation - a page load's own requests aren't attributable to one
component's interaction the way a click/fill's are. crawl4ai's own
listener setup/teardown is scoped to this single `arun()` call (confirmed
by reading `async_crawler_strategy.py`: `captured_requests = []` is a
fresh local list per call, and the request/response/requestfailed
listeners are explicitly removed in a `finally:` block before returning -
no cross-call accumulation on a reused session).

## _interact-success-signal

`result.success` can be `False` for a reason that has nothing to do with
whether *our* interaction succeeded: crawl4ai's own anti-bot heuristic
(`async_webcrawler.py::is_blocked`) runs *after* every hook - including
`on_execution_ended`, where the stashed `action_result` already got set -
and vetoes the whole call's `success` to `False` whenever the resulting
page's content looks like a block/challenge page (confirmed live on
austral.edu.ar: a click that genuinely, correctly navigated - the
`on_execution_ended` hook logged `success: True, navigated: True` for
it - still turned into an unconditional `RuntimeError` here, discarding
the navigation this class's own code had already captured, because the
destination happened to be an anti-bot challenge shell with no `<body>`
tag). `redirected_url` itself is untouched by that check (only
`success`/`error_message` are - see `async_webcrawler.py`), so
`page_state.py::resolved_url()` still resolves correctly even when this
happens.

`action_result` is this class's own, earlier, more specific signal (set
by `on_execution_ended`) - read it before deciding whether
`result.success == False` is actually fatal, so a real navigation that
crawl4ai's own later heuristic second-guesses isn't silently thrown away
as an unexplained failure.

## resync

Re-run discovery against the *current* live DOM of an existing
`session_id` session, without performing any action and without
navigating - a no-op `js_code` that only sets the success marker, so
`_interact()`/`on_execution_ended()`'s real re-extraction runs exactly
as it does after a genuine click/fill.

Exists for the mechanical loop's stale-selector recovery (see
`docs/dev/spiders/orchestration/page_visitor/recovery.md#_recover_stale_frontier`):
after an "element not found" failure, the caller needs a fresh
components/links snapshot to check whether the failure was caused by an
unrelated DOM remount (e.g. a component-library subtree reassigning its
ids) - `discover_page()` isn't usable here since it performs a full
navigation, discarding same-page state a same-URL resync must preserve.

## go_back

Step the `session_id` session's browser history back one entry -
`history.back()` as the `js_code`, going through the same
`_interact()`/`on_execution_ended()` path as `click`/`fill`/`resync`, not
`discover_page()`.

Exists for the mechanical loop's physical-navigation resume (see
`docs/dev/spiders/orchestration/page_visitor/recovery.md#return_to_origin`):
once a click has physically navigated somewhere, the caller needs to get
back to the page it left - but `discover_page()` performs a *fresh*
navigation, a brand-new request against the target server for a page this
same session was just rendering a moment ago. `history.back()` instead
lets the browser reuse whatever it already has for that history entry
(bfcache, or at minimum the ordinary HTTP cache) the same way a person
clicking their browser's own Back button would.

Confirmed live on austral.edu.ar: before this existed, a resume's
`discover_page()` re-fetch of the origin was a second navigation
to the same URL within seconds of the first, and `TargetLoadThrottle`
(`docs/dev/spiders/browser/target_load_throttle.md#module`) - built for
exactly this site's own history of degrading under repeated load -
recorded the second fetch taking visibly longer than the first (2.77s ->
4.21s in one observed run) as the target itself pushing back.

Not routed through `TargetLoadThrottle` at all - consistent with every
other `_interact()`-based method (`click`/`fill`/`resync`), none of which
record a navigation either. A `go_back` that does end up costing the
target a real request is still far cheaper than a full `discover_page`
navigation would have been, so under-counting it here is the accepted
tradeoff, not an oversight.

Returns whatever `PageState` the browser lands on - the caller
(`NavigationRecovery.return_to_origin`) is responsible for checking that's
actually the page it expected back, since `history.back()` can return
without error even when nothing meaningful happened (an empty history
stack, or a client-side router swallowing the `popstate` event).

## click

Click `selector` within the `session_id` session and return the new
`PageState`. Dispatches a real DOM click via `el.click()` - unlike
Playwright's own `page.click()`, this has no actionability/visibility
checks of its own, so the caller (the mechanical interaction loop) is
expected to only offer already-`visible` components from discovery,
rather than relying on a click-time visibility retry the way
`PlaywrightScraper.click()` did.

## fill

Type `value` into `selector` within the `session_id` session and return
the new `PageState`.

Sets the value via the native property setter (not plain `el.value =
...`) and dispatches `input`/`change` events - required for React/Vue-
controlled inputs to actually register the change, since those
frameworks intercept the setter on their own rendered `value` property
and otherwise never see a directly-assigned value.

## close_session

Releases the Playwright page/context crawl4ai opened for `session_id` -
a thin wrap of `crawler_strategy.kill_session` (the same object
`__aenter__` already reaches to register hooks), so this class stays the
single seam this codebase touches crawl4ai through.

**Three different things this method has been used for, in order** (all
confirmed live on austral.edu.ar, all real, none of them fictional):

1. *Per-URL, every distinct page* - the original design: every URL got
   its own `session_id = url`, and crawl4ai's `BrowserManager.get_page()`
   opens a brand-new page for any unseen `session_id` and keeps it alive
   indefinitely. Nothing ever called this method, so tabs piled up one
   per page for the whole crawl; `[FETCH]` timing climbed from ~1s early
   in a run to 30-40s later in the same run.
2. *Per-visit, every single page* - the first fix: closed after every
   `PageVisitor.visit()`. Wrong in a different way - this project's
   `CrawlerRunConfig` never varies per page, so every session shares one
   config-signature-keyed browser *context*
   (`browser_manager.py`'s `contexts_by_config`); closing a session drops
   that context's last reference and crawl4ai tears the *whole context*
   down, so the very next page paid for building a brand-new context from
   scratch - more expensive than the one leaked page it replaced, and
   with `page_concurrency=1` (the default) this happened on *every*
   page, not just occasionally.
3. *Periodically, every `session_recycle_after` visits* - the actual
   fix, and the only thing that still calls this method today. See
   `docs/dev/spiders/orchestration/mechanical_loop/loop.md#_recycle_session_if_due`
   for why: it isn't a tab-count problem or a context-churn problem at
   all, it's the target *website's* own client-side JS (ads/analytics/
   GTM, extremely common on real WordPress sites) accumulating JS heap
   and DOM event listeners across many navigations that share one
   long-lived tab - a full `page.goto()` does not reset this, because
   these origins' service workers/trackers hold their own references
   across the navigation. Measured directly against austral.edu.ar with
   raw Playwright (bypassing crawl4ai, to rule out any crawl4ai-side
   cause): one persistent tab climbed from ~9MB JS heap / ~90 event
   listeners to ~700MB / ~11000 listeners over 50 real page navigations,
   with the browser's own major garbage-collection pauses landing
   exactly on the slowest observed navigations (a 9.15s one coincided
   with heap collapsing from 745MB back down to 264MB mid-run). Closing
   and reopening the *page* (not the whole context - cookies/consent-
   banner state and the context stay alive) every 15 visits reset heap
   to single-digit MB and listeners to double digits every time, with no
   runaway growth and no context-rebuild tax paid per page.

`kill_session` closes the page unconditionally and only tears the shared
context down if this was that context's last active page - with
`page_concurrency=1` that's every single recycle, same context-rebuild
cost as approach 2 above, just paid once per `session_recycle_after`
visits instead of once per visit. See
`docs/dev/spiders/orchestration/mechanical_loop/config.md#session_recycle_after`
for picking that number.

**Update - bounded by `session_cleanup_timeout_seconds`, a second
deadlock site distinct from `arun()`'s own**: `navigation_watchdog_seconds`
(`#_run_with_watchdog` above) bounds `discover_page`/`_interact`'s own
`arun()` call, but this method's call into `kill_session` was a
completely separate, still-unguarded path into the same category of
crawl4ai-internal code - confirmed live on austral.edu.ar as a genuine,
reproduced-twice deadlock: a `two_phase_crawl` scout sweep froze for 5+
minutes with `navigation_watchdog_seconds` (60s) long since elapsed and
no recovery, which live process forensics (`py-spy dump`) showed was
*not* stuck inside `arun()` or the graph-store writer - both sat
completely idle. The one remaining periodic call this method's own
callers make (`_recycle_session_if_due`, every `session_recycle_after`
visits) was the best-supported remaining candidate: unguarded, reaches
crawl4ai's own session/browser-management internals, and fires only
occasionally, matching the observed "runs fine for dozens of visits,
then freezes" pattern.

Wrapped here, at the one definition, rather than at each of the two
callers (`_recycle_session_if_due` in `loop.py`, and this file's own
`_force_close_wedged_session`) - both get the bound for free, and
`_force_close_wedged_session` could drop its own now-redundant
`asyncio.wait_for` wrapper entirely. `_recycle_session_if_due` needed no
code change at all: its existing broad `except Exception` already turns
whatever this raises into a logged warning and a continued crawl,
exactly the recovery a hung recycle attempt needs.

Same honesty as `navigation_watchdog_seconds`'s own doc: this bounds and
recovers from a hang in crawl4ai's own internals, it does not fix
whatever's actually contended inside them.
