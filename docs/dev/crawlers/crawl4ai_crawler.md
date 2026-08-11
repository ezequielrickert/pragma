# `src/crawlers/crawl4ai_crawler.py`

## module

crawl4ai-backed page discovery (Phase 1 of the crawl4ai migration - see
`wiki/` and the approved plan for background).

This module proves and exposes exactly one thing: that
`PlaywrightScraper._discover_components`'s battle-tested discovery JS
(unique selectors, full ARIA-role coverage, shadow-DOM piercing,
accessible-label fallback chain, per-frame discovery) runs unmodified
inside a crawl4ai hook, driven by a real `AsyncWebCrawler`/`Playwright`
page instead of Pragma's old sync, lazily-started single `Page`. No
interaction (click/fill), no Neo4j writes, and no AI call happen here -
those are Phase 2+ (see the plan file for the full phase breakdown).
`Crawl4AICrawler.discover_page()` is the single entry point: navigate to
a URL, run every read-only extraction pass, return a `PageState`.

Confirmed via a spike against a local fixture server before this was
written (recorded in the plan file's "Phase 0 spike" section):
- `before_retrieve_html` fires after `wait_for` but *before* any
  `js_code` on the same `arun()` call executes - correct for this
  module's plain-navigation discovery pass, but NOT correct for
  re-discovering after a scripted interaction (see `_on_execution_ended`,
  wired here but unused until Phase 2's mechanical interaction loop
  starts passing `js_code`).
- `on_execution_ended` fires immediately after `js_code` runs - the hook
  Phase 2's post-click/fill re-discovery must use instead.
- A hook is a plain `async def` callable with no return channel back
  into `arun()`'s result, so discovery output is stashed in
  `self._stash`, keyed by `session_id`, and read back by the calling
  method after `arun()` returns.

## _action_mark

A window property used to hand a click/fill's own success/failure back
to Python - crawl4ai's `robust_execute_user_script` logs-and-continues on
a `js_code` error rather than failing the `arun()` call (confirmed by
reading `async_crawler_strategy.py`), which would otherwise repeat the
exact swallowed-failure bug wiki/browser-automation-pitfalls.md documents
for `PlaywrightScraper.click()`'s old bare try/except. Wrapping every
click/fill in its own try/catch that writes here, then reading it back
explicitly in `_on_execution_ended`, is what makes a real action failure
raise instead of silently looking like a no-op.

## _blocked_resource_types

Resource types genuinely safe to drop for component discovery/interaction
purposes when `Crawl4AICrawler.block_images` is enabled - never
"stylesheet" (layout affects visibility/rect discovery), never
"script"/"xhr"/"fetch"/"document" (would break the SPA itself). Real
bandwidth/time savings, unlike crawl4ai's own `exclude_external_images` -
see `Crawl4AICrawlerConfig`'s `block_images` entry for why that flag
doesn't touch the network layer at all.

## _is_navigation_context_error

Whether `exc` is Playwright's specific "the JS execution context was torn
down because the page navigated" error - not a generic evaluate failure.
Matched by substring since Playwright doesn't expose this as a distinct
exception type; the message text itself is Playwright's own, stable
diagnostic wording for exactly this condition.

## _adaptive_wait_step_seconds

`_wait_for_new_content`'s poll step (`_ADAPTIVE_WAIT_STEP_SECONDS`,
100ms) - a module-level constant, not a config field, since it's the
resolution of the poll itself, not a per-site tuning decision the way
`wait_seconds` is.

## _wait_for_new_content

Replaces a flat `asyncio.sleep(ceiling_seconds)` with a short-step poll
that returns the moment new content appears, still bounded by the same
`ceiling_seconds` a flat sleep would have spent regardless.

**A first attempt at this used plain DOM-stability (stop once the DOM
stops changing) and was wrong** - reverted after it broke both
`test_wait_seconds_finds_content_rendered_after_a_delay` and
`test_interaction_wait_seconds_controls_post_click_settle_delay`.
`delayed_render.html`'s content arrives via a one-shot `setTimeout`, not
continuous mutation - the DOM is perfectly static for the 1.5s *before*
the timer fires, which looks identical to "already settled" to a
stability check. No amount of DOM-diffing can tell those two states
apart before the timer actually fires - this is a hard limit, not a
tuning problem. Kept as a lesson here since the same mistake is easy to
re-derive from a plain intent to "detect when the page is settled."

The actual signal used instead: `DISCOVER_COMPONENTS_JS`'s own component
count, checked against `baseline_count`.
- `baseline_count=None` (used by `_before_retrieve_html`, a fresh
  navigation with no prior snapshot for this session) - any component
  count above zero is real forward progress, safe to stop on
  immediately. This is what makes `test_wait_seconds_finds_content_
  rendered_after_a_delay` finish in ~1.5s instead of the full configured
  ceiling once `delayed_render.html`'s button actually appears.
- `baseline_count=<pre-click count>` (used by `_on_execution_ended`) -
  a page already has components before any interaction (the very
  element that was just clicked, at minimum), so "any content" would
  trivially satisfy on the *first* poll and exit before a delayed reveal
  ever had a chance to appear. Comparing against the exact pre-click
  count (read from `self._stash[session_id]`, the snapshot
  `_before_retrieve_html` or the previous interaction left behind)
  instead requires a genuine *change*, which is what
  `test_interaction_wait_seconds_controls_post_click_settle_delay`
  actually exercises.

A page whose component count never changes (a click that reveals
nothing, or a page with no delayed content at all) simply spends the
full `ceiling_seconds`, identical to the original flat-sleep behavior -
never worse, only faster when there's something to detect early.
Returns silently (no exception) on a torn-down execution context -
`page.evaluate` failing here almost always means a navigation happened
mid-poll, and the caller's own extraction (`run_extraction`, called
right after) is what actually needs to react to that, not this check.

## _backoff_slowdown_multiplier

How many times slower than the fastest navigation seen this crawl counts
as the *target server* straining rather than ordinary page-to-page
variance (heavier pages are always somewhat slower than light ones, on
any healthy server). 2.0 is deliberately generous - see `_update_backoff`
for why a tighter multiplier would misfire on normal variance.

## _backoff_step_seconds

Fixed additive step backoff grows or decays by per navigation - the
"AIMD" (additive-increase/additive-decrease) shape, the same family of
congestion-control algorithm TCP itself uses for exactly this problem
(a shared resource getting slower under load, with no way to know its
true capacity in advance). Additive rather than multiplicative in both
directions deliberately: a doubling-style backoff would either overshoot
wildly on the first slow request or take too long to notice a real,
sustained slowdown - a fixed step converges smoothly either way.

## _backoff_seconds

Lives on the `Crawl4AICrawler` instance, not per-session/per-worker -
deliberately shared across every concurrent worker, since they're all
hitting the *same* target server and a slowdown one worker observes is
real evidence about that shared resource, not something scoped to just
that worker's own tab. No lock around the read-modify-write in
`_update_backoff`: a `page_concurrency > 1` race between two workers
updating this concurrently can only ever under- or over-count a single
`_BACKOFF_STEP_SECONDS` step, self-corrects on the very next navigation
either worker makes, and Python's GIL means a plain float assignment
can't produce a torn/corrupted value - not worth a lock for a backstop
that was never meant to be exact (same discipline `max_pages`'s own soft
bound already documents in `docs/dev/crawlers/mechanical_loop.md#_worker`).

## _throttle_for_target_load

Sleeps off the crawl's *current* backoff before every navigation - called
unconditionally; a no-op when `_backoff_seconds` is still 0 (the common
case for a target that isn't straining).

## _update_backoff

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
client-side fix (session recycling, heap clearing, anything else in this
file) can touch, since the plain-HTTP measurement showed the identical
pattern with none of that machinery even running.

AIMD update, called once per navigation with its actual elapsed wall
time: tracks the fastest navigation seen so far as the crawl's own
estimate of "how fast this target can be, unloaded" (a floor, not an
average - one fast sample is proof the target *can* respond that fast,
so a single early lucky low sample is a legitimate reference point, not
noise). A navigation more than `_BACKOFF_SLOWDOWN_MULTIPLIER` times that
floor is treated as the target showing strain, growing backoff by one
step (capped at `backoff_ceiling_seconds`); anything closer decays it by
the same step (floored at 0). `backoff_ceiling_seconds=None` skips all of
this - both the fastest-navigation tracking and the update itself -
entirely, so a caller that never wants backoff pays nothing for it.
Deliberately scoped to `discover_page` only, not `_interact` (the shared
`click`/`fill`/`resync` implementation): a `js_only=True` interaction
call almost never re-fetches the origin at all (it manipulates the
already-loaded DOM in place), so its timing reflects local browser/JS
cost, not target-server load - mixing the two into one signal would
corrupt the "fastest seen" floor with numbers an order of magnitude
smaller than a real navigation, making ordinary navigations look like a
slowdown on every single one.

## Crawl4AICrawlerConfig

Every tuning knob `Crawl4AICrawler` accepts. Bundled into one object
(mirroring `Neo4jConfig` in `src/storage/neo4j_graph_store.py`) instead
of a long constructor argument list.

- `headless`: Run the browser without a visible UI.
- `wait_seconds`: **Ceiling** on how long to let the page settle before
  running discovery on a plain navigation (`_before_retrieve_html`) -
  carried over from `PlaywrightScraper`'s own `wait_seconds` (same name,
  same purpose), which this module's initial port dropped by mistake.
  Confirmed live against empanad.app (a React SPA): `wait_for="css:body"`
  alone is satisfied by the pre-hydration HTML shell, so discovery ran
  against effectively empty content - `<title>`/meta description/tags
  were all present (server-rendered/static), but `components`/`links`
  came back at 0 every time, on a page that stably has real interactive
  elements once actually rendered. Not a flat sleep - see
  `_wait_for_new_content` above: a page that renders fast rarely spends
  this in full, one that needs the whole ceiling still gets it. Default
  is deliberately small (fixture/test pages need none of this); raise it
  (or pass a site-specific value) for JS-heavy real sites - see
  `PragmaConfig.wait_seconds`.
- `interaction_wait_seconds`: Same purpose, applied after a
  click/fill/resync's own re-discovery (`_on_execution_ended`) instead.
  Also a ceiling, not a flat sleep - same `_wait_for_new_content`
  mechanism, keyed off the pre-click component count instead of "any
  content." Split out from `wait_seconds` because the two aren't the same
  cost in practice: a full page's first hydration is genuinely slow, but
  a same-page DOM update from one click is usually much faster to settle
  - confirmed live: ~145 interactions in one real crawl, each paying
  `wait_seconds` twice before this knob existed - once here, once in
  `_before_retrieve_html`'s own sleep that a post-interaction
  re-discovery doesn't even use - dominated that run's wall-clock time.
  `None` (default) falls back to `wait_seconds` unchanged - existing
  callers that only ever set one knob keep identical behavior; set this
  explicitly, lower than `wait_seconds`, once a site's interaction updates
  are confirmed to settle faster than its initial hydration.
- `debug_log`: If given, every crawl4ai hook firing gets appended to
  `debug_log.md` (see `debug_log.py`), and each successful
  navigation/interaction saves crawl4ai's own markdown conversion of the
  resulting page to `debug_log`'s `pages/` directory. `None` (default)
  disables all of this - purely additive, no behavior changes when
  omitted.
- `page_timeout_seconds`: crawl4ai's own `CrawlerRunConfig.page_timeout`
  (the raw navigation/goto dead-page timeout, in ms once converted) - a
  *different* knob than `wait_seconds`/`interaction_wait_seconds` above,
  which are our own extra settle sleep applied *after* a page/interaction
  has already loaded. `page_timeout` bounds how long crawl4ai waits for
  the underlying `goto()`/`js_only` call itself to resolve at all before
  giving up outright. crawl4ai's own default is 60s - fine for
  correctness, wasteful for a genuinely hung/dead request, which then eats
  a full minute before this crawler ever finds out. Default here (15s) is
  comfortably above the `wait_seconds` settle times this project has
  actually needed for real SPA hydration (empanad.app/austral.edu.ar -
  see wiki/crawl4ai-integration-pitfalls.md) while still cutting a truly
  hung request down from a full minute. Do not set this anywhere near
  `wait_seconds`'s own scale (a few seconds) - that bounds the wrong phase
  and reintroduces the "0 components discovered" pre-hydration-shell bug
  that doc documents, just via a different code path.
- `prefetch`: Passed through to crawl4ai's own
  `CrawlerRunConfig.prefetch`, which short-circuits crawl4ai's
  markdown-generation/content-scraping pipeline entirely (confirmed by
  reading `async_webcrawler.py`) - a real, meaningful cost this class
  never actually needed in the first place, since every fact it reads
  (`components`/`links`/`description`/`text_content`) comes from this
  module's own JS run via hooks that fire *before* that pipeline, never
  from crawl4ai's extraction. Default `False` because of one real side
  effect: `prefetch=True` also means `result.markdown` comes back empty,
  which silently empties out `_save_markdown`'s `debug_log`/`pages/*.md`
  snapshots - opt in explicitly once you've decided you don't need those
  for a given run (e.g. a bulk/production crawl, as opposed to an active
  debugging session that still wants to read them per
  wiki/debugging-agent-systems.md's discipline).
- `block_images`: If True, aborts image/media/font *network requests*
  outright via a Playwright `page.route()` handler installed in
  `on_page_context_created` - genuine bandwidth/load-time savings, unlike
  crawl4ai's own `exclude_external_images` (confirmed by reading
  `content_scraping_strategy.py`: that flag only strips `<img>` tags from
  crawl4ai's own post-fetch markdown/media output *after* the browser has
  already downloaded them - zero network savings, and this class never
  reads that output anyway). Default `False` since it's a real behavior
  change (some sites use image `load`/`error` events, or an image's
  rendered size, to drive layout/lazy-load logic that component discovery
  could then see differently) - opt in once you've confirmed the target
  site's interactive elements don't depend on images actually loading.
- `interaction_timeout_seconds`: A *third* timeout phase, distinct from
  both `page_timeout_seconds` (bounds the raw `goto()`/`js_only` fetch)
  and `wait_seconds`/`interaction_wait_seconds` (our own settle sleep
  *after* a load already succeeded) - this one bounds Playwright's own
  *unbounded-by-default* internal waits inside a single interaction
  round-trip, which neither of the above ever touches. Confirmed live on
  austral.edu.ar (see wiki/crawl4ai-integration-pitfalls.md's "a session
  parked on a page that never finishes loading" entry): once a click
  navigates the session to a page whose `domcontentloaded` event never
  fires (a WAF holding the response open as an anti-automation measure,
  observed serving a body-less "no `<body>` tag" 8653-byte shell),
  crawl4ai's own `robust_execute_user_script` calls
  `page.wait_for_load_state("domcontentloaded")` with **no explicit
  timeout at all** - every single subsequent interaction against that
  session then silently inherits Playwright's own hardcoded 30000ms
  default, one full 30s wait per attempt, for as many components as the
  page has left. `page.set_default_timeout()` (called once per `arun()`
  call, in `_on_page_context_created`) changes what *that* implicit
  default resolves to - it only affects calls with no explicit timeout of
  their own, so `page_timeout_seconds`'s own already-explicit
  `goto()`/`js_only` timeout is untouched. `None` (default) leaves
  Playwright's own 30000ms default in place - opt in once a site's shown
  this exact failure shape; see `MechanicalCrawler`'s consecutive-failure
  circuit breaker (`docs/dev/crawlers/page_visitor.md#_max_consecutive_unexplained_failures`)
  for the complementary fix that actually stops burning attempts once a
  session looks dead, rather than just making each dead attempt cheaper.
- `backoff_ceiling_seconds`: Cap on the polite delay `_throttle_for_target_load`
  grows between navigations once the *target server itself* is slowing
  down under this crawl's own request load - see `_update_backoff` below
  for the mechanism and the live measurement this default (5.0) is based
  on. `None` disables backoff entirely (zero overhead per navigation, for
  a target already confirmed fast/robust, or a test fixture that never
  needs it).

## Crawl4AICrawler

Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with`
block - matching crawl4ai's own browser-lifecycle model (start once, run
many `arun()` calls, close once) rather than Pragma's old per-action
lazy-start model. Use as:

```python
async with Crawl4AICrawler() as crawler:
    state = await crawler.discover_page(url)
```

## __aenter__-hook-order

Hooks must be registered *before* `__aenter__()` is awaited below -
confirmed by reading crawl4ai's own source: `on_browser_created` fires
from inside `crawler_strategy.start()`, which `AsyncWebCrawler.__aenter__()`
calls immediately. Registering after `__aenter__()` (this module's
original order) means that specific hook's callback is set too late to
ever see its own firing.

## __aenter__-single-slot-hooks

Always registered (not gated on `debug_log`) - `_on_page_context_created`
is where `block_images`'s route handler gets installed regardless of
debug logging; it folds in the log-only behavior itself when `debug_log`
is set, since crawl4ai only allows one callback per hook name (confirmed:
`self.hooks` is a single-slot dict per hook type, not a list) -
registering a second handler here would silently replace, not add to,
this one.

## _log_only_hook

Build a hook callback that only logs to `self.debug_log`, for the
crawl4ai hooks this class has no functional use for
(`on_browser_created`/`on_page_context_created`/`on_user_agent_updated`/
`on_execution_started`/`before_goto`/`after_goto`/`before_return_html`)
but the user wants a debug record of anyway - "every event that triggers
a hook" should show up in `debug.md`, not just the two this class already
reads discovery data from. See `docs/dev/crawlers/debug_log.md#log_hook_from_raw`
/`#loggable_hook_details` for which fact each hook type actually carries.

The inner `hook(*args, **kwargs)` closure is a plain sync callable, not
`async def` - crawl4ai's `execute_hook` checks
`asyncio.iscoroutinefunction()` and calls either way, and this does no
awaiting of its own, just formatting + a synchronous file write via
`self.debug_log`.

## _on_page_context_created

Registered unconditionally (see `__aenter__-single-slot-hooks`) - installs
`block_images`'s route handler when enabled, and folds in the same
log-only behavior `_log_only_hook` would otherwise provide for this hook
when `debug_log` is set (crawl4ai allows only one callback per hook name -
see `__aenter__-single-slot-hooks`).

Fires on *every* `arun()` call for a session, not just when a new page is
actually created (confirmed by reading `async_crawler_strategy.py`: this
hook runs unconditionally right after `browser_manager.get_page()`,
whether that returned a fresh page or a cached, reused one) - so the
route handler is guarded by a flag stashed directly on the `page` object,
the same "don't double-inject" pattern crawl4ai's own
navigator-overrider/shadow-DOM hooks already use on `context`, to avoid
stacking a duplicate `page.route()` handler on every single interaction
against an already-routed, reused page.

## _on_page_context_created-timeout

Changes what Playwright's *own* internal waits (e.g.
`robust_execute_user_script`'s un-timed
`wait_for_load_state("domcontentloaded")`) fall back to when they carry
no explicit timeout of their own - see `Crawl4AICrawlerConfig`'s
`interaction_timeout_seconds` entry for the exact failure this fixes.
Safe to call on every `arun()` (no "already installed" guard needed,
unlike the route handler above - this is a plain property set, not a
stacking handler).

## _before_retrieve_html

Discovery point for a plain navigation pass (no `js_code` on this
`arun()` call) - see the `module` section above for why this hook is
specifically wrong for a post-interaction re-discovery.

## _on_execution_ended

Discovery point for the interaction-followup case: fires immediately
after `config.js_code` runs, so it sees post-interaction DOM state. Also
reads back `_ACTION_MARK` (see `_action_mark` above) so `click()`/`fill()`
below can tell a real failure from a successful no-op, instead of
trusting crawl4ai's own swallow-and-log behavior for a failed `js_code`
execution.

A click/fill that itself triggers real navigation (a plain `<a href>`, or
an onclick that sets `location`) destroys the JS execution context
**synchronously, mid-statement** - confirmed empirically: our own
click/fill JS is a single IIFE that calls `el.click()` and *then* assigns
`_ACTION_MARK` on the next line, but for a navigating click, the browser
starts unloading the page the moment `el.click()` runs, so the
`_ACTION_MARK` assignment never executes at all - not even a no-op, the
whole rest of the script silently never ran, on the old page or the new
one.

crawl4ai's own `robust_execute_user_script` (which produces `result`,
this hook's kwarg) already anticipates exactly this: it catches
Playwright's "Execution context was destroyed" error internally, waits
out `load` + `networkidle` on whatever page navigation landed on, and
returns `{"success": True, "info": "Navigation triggered..."}` - all of
this happens *before* this hook fires. That makes `result` the
authoritative signal for the navigating-click case, and it's why this
method reads `_ACTION_MARK` first (the precise success/failure our own
click()/fill() JS explicitly set, for the common non-navigating case) and
only falls back to `result` when the marker comes back unset - which, per
the above, means a navigation pre-empted it, not that the action silently
did nothing. Treating a missing marker as an unconditional failure (an
earlier version of this method did exactly that) was actively dangerous:
the caller then believed the click was a no-op and kept issuing further
clicks/fills from the *same* pass, each evaluated against selectors that
belonged to a page no longer there - confirmed to cascade into "element
not found" errors on every subsequent component in that pass, not just
the one that actually navigated.

## _on_execution_ended-navigation-retry

crawl4ai's own `robust_execute_user_script` already waits out a
navigation before this hook fires (see `_on_execution_ended` above), but
if discovery still races ahead of it in some edge case, give the new page
one more chance to settle before retrying extraction.

## _on_execution_ended-fallback

`marked is False`: evaluate itself failed for a reason other than a
navigation tearing down the context - a genuine, otherwise-unexplained
failure to even read the marker back.

Marker was never set (`None`, or evaluate raised the
navigation-destroyed error): fall back to crawl4ai's own execution
result, which already resolved whether this was a real navigation.

## discover_page

Navigate to `url` and return its `PageState` - components, links,
description, metadata, all via read-only extraction. No interaction.

`session_id` defaults to `url` when the caller doesn't pass one, so a
call made in isolation never races another on the same `self._stash`
key. `MechanicalCrawler` passes its own explicit `session_id` instead -
one stable value per worker, reused across every URL that worker visits
in turn - so a whole crawl reuses `page_concurrency` browser tabs rather
than opening a new one per page. See
`docs/dev/crawlers/mechanical_loop.md#_worker` and
`docs/dev/crawlers/page_visitor.md#visit`.

## _resolved_url

`result.url` is always the *requested* URL, unchanged regardless of what
actually happened - confirmed empirically: after a `js_only` click that
navigates to a different page, `result.url` still echoed the original URL
while `result.redirected_url` correctly held the real destination.
`redirected_url` is crawl4ai's own field for "the page we actually ended
up on" (it explicitly re-reads `page.url` right before returning
specifically to capture JS-driven navigation - see
`async_crawler_strategy.py`'s own comment on that line).

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
See `docs/dev/crawlers/mechanical_loop.md#in_flight` for the deeper fix
(preventing two of those sessions from ever running concurrently in the
first place) - this key change is a second, independent layer: even a
legitimate, non-concurrent, sequential resume of the *same* session
correctly keeps overwriting its own file (the intended "live snapshot"
behavior), while two genuinely *different* sessions that happen to
redirect to the same destination now keep their own separate,
inspectable files instead of one clobbering the other.

Not `session_id` either, now that `session_id` names a *reused browser
tab* rather than a page: since `MechanicalCrawler` hands every worker's
whole run of URLs the same `session_id` (see `#discover_page` above),
using it here would collapse every page one worker ever visits onto a
single markdown filename. `url` is the one identifier that's still
one-per-page regardless of how many pages end up sharing a tab.

## _interact

Run `js_code` against the existing `session_id` session (no full
navigation - `js_only=True`) and return the resulting `PageState`,
re-discovered via `_on_execution_ended`.

A real action failure (element not found, a raised JS exception)
propagates as a `RuntimeError` - the primary action must never look like
a successful no-op, per wiki/browser-automation-pitfalls.md. `session_id`
must be the same one `discover_page()` was called with for this URL, so
this reuses the live page/session instead of triggering a fresh
navigation.

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
`on_execution_ended`, where `self._stash`'s `action_result` already got
set - and vetoes the whole call's `success` to `False` whenever the
resulting page's content looks like a block/challenge page (confirmed
live on austral.edu.ar: a click that genuinely, correctly navigated - our
own `on_execution_ended` hook logged `success: True, navigated: True` for
it - still turned into an unconditional `RuntimeError` here, discarding
the navigation this class's own code had already captured, because the
destination happened to be an anti-bot challenge shell with no `<body>`
tag). `redirected_url` itself is untouched by that check (only
`success`/`error_message` are - see `async_webcrawler.py`), so
`_resolved_url()` still resolves correctly even when this happens.

`action_result` is this class's own, earlier, more specific signal (see
`_on_execution_ended` above) - read it before deciding whether
`result.success == False` is actually fatal, so a real navigation that
crawl4ai's own later heuristic second-guesses isn't silently thrown away
as an unexplained failure.

## resync

Re-run discovery against the *current* live DOM of an existing
`session_id` session, without performing any action and without
navigating - a no-op `js_code` that only sets the success marker, so
`_interact()`/`_on_execution_ended()`'s real re-extraction runs exactly
as it does after a genuine click/fill.

Exists for the mechanical loop's stale-selector recovery (see
`docs/dev/crawlers/page_visitor.md#_recover_stale_frontier`): after an
"element not found" failure, the caller needs a fresh components/links
snapshot to check whether the failure was caused by an unrelated DOM
remount (e.g. a component-library subtree reassigning its ids) -
`discover_page()` isn't usable here since it performs a full navigation,
discarding same-page state a same-URL resync must preserve.

## click

Click `selector` within the `session_id` session and return the new
`PageState`. Dispatches a real DOM click via `el.click()` - unlike
Playwright's own `page.click()`, this has no actionability/visibility
checks of its own, so the caller (the mechanical interaction loop, Phase
2) is expected to only offer already-`visible` components from discovery,
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
   `docs/dev/crawlers/mechanical_loop.md#_recycle_session_if_due` for
   why: it isn't a tab-count problem or a context-churn problem at all,
   it's the target *website's* own client-side JS (ads/analytics/GTM,
   extremely common on real WordPress sites) accumulating JS heap and
   DOM event listeners across many navigations that share one
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
`docs/dev/crawlers/mechanical_loop.md#session_recycle_after` for picking
that number.
