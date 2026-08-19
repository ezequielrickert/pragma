# `spiders/browser/crawl4ai_crawler/config.py`

## module

Every tuning knob `Crawl4AICrawler` accepts, bundled into one object
(mirroring the per-provider `Config` dataclass pattern every agent/
graph-store module uses, e.g. `DuckDBGraphStore`'s own connection
settings) instead of a long constructor argument list. Pure data - no
logic of its own, which is
exactly why it's its own file: a change here is never a change to how a
hook fires or how a page gets navigated.

## Crawl4AICrawlerConfig

- `headless`: Run the browser without a visible UI.
- `storage_state_path`: see `#storage_state_path` below.
- `wait_seconds`: **Ceiling** on how long to let the page settle before
  running discovery on a plain navigation (`before_retrieve_html`, see
  `docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#before_retrieve_html`) -
  carried over from `PlaywrightScraper`'s own `wait_seconds` (same name,
  same purpose), which this module's initial port dropped by mistake.
  Confirmed live against empanad.app (a React SPA): `wait_for="css:body"`
  alone is satisfied by the pre-hydration HTML shell, so discovery ran
  against effectively empty content - `<title>`/meta description/tags
  were all present (server-rendered/static), but `components`/`links`
  came back at 0 every time, on a page that stably has real interactive
  elements once actually rendered. Not a flat sleep - see
  `docs/dev/spiders/browser/dom_settle.md#_wait_for_new_content`: a page
  that renders fast rarely spends this in full, one that needs the whole
  ceiling still gets it. Default
  is deliberately small (fixture/test pages need none of this); raise it
  (or pass a site-specific value) for JS-heavy real sites - see
  `PragmaConfig.wait_seconds`.
- `interaction_wait_seconds`: Same purpose, applied after a
  click/fill/resync's own re-discovery (`on_execution_ended`) instead.
  Also a ceiling, not a flat sleep - same `_wait_for_new_content`
  mechanism, keyed off the pre-click component count instead of "any
  content." Split out from `wait_seconds` because the two aren't the same
  cost in practice: a full page's first hydration is genuinely slow, but
  a same-page DOM update from one click is usually much faster to settle
  - confirmed live: ~145 interactions in one real crawl, each paying
  `wait_seconds` twice before this knob existed - once here, once in
  `before_retrieve_html`'s own sleep that a post-interaction
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
  call, in `on_page_context_created`) changes what *that* implicit
  default resolves to - it only affects calls with no explicit timeout of
  their own, so `page_timeout_seconds`'s own already-explicit
  `goto()`/`js_only` timeout is untouched. `None` (default) leaves
  Playwright's own 30000ms default in place - opt in once a site's shown
  this exact failure shape; see `PageVisitor`'s consecutive-failure
  circuit breaker
  (`docs/dev/spiders/orchestration/page_visitor/visitor.md#_max_consecutive_unexplained_failures`)
  for the complementary fix that actually stops burning attempts once a
  session looks dead, rather than just making each dead attempt cheaper.
- `backoff_ceiling_seconds`/`circuit_breaker_cooldown_seconds`: see
  `viewport`/`backoff_ceiling_seconds`/`circuit_breaker_cooldown_seconds`
  sections below.

## storage_state_path

Playwright `storage_state` JSON path to restore cookies/localStorage
from - `None` (crawl4ai's own default) launches a fresh, anonymous
browser context. Set by a caller's own login-resolution step
(`spiders/browser/login.py::ensure_login_session`/`force_login_session`)
before the real crawl starts; wired straight into `BrowserConfig`'s own
`storage_state` in `Crawl4AICrawler.__aenter__` - a browser-context-level
setting, not a per-`arun()` one, since the whole point is every
navigation in this crawl sharing the one authenticated context.

## viewport

Small (800x600) on purpose - less render cost per navigation. Nothing in
this pipeline needs a realistic viewport, so there is no second, larger
value to override it with.

## backoff_ceiling_seconds

Cap on the polite delay `TargetLoadThrottle` grows between navigations
once the target server itself is slowing down under this crawl's own
request load - see `docs/dev/spiders/browser/target_load_throttle.md`
for the mechanism and the live measurement this default is based on.
`None` disables backoff entirely (zero overhead per navigation, for a
target already confirmed fast/robust, or a test fixture that never needs
it).

## circuit_breaker_cooldown_seconds

How long every worker pauses once `TargetLoadThrottle`'s circuit breaker
trips - a navigation `_SEVERE_SLOWDOWN_MULTIPLIER` times the crawl's own
fastest. See `docs/dev/spiders/browser/target_load_throttle.md#_trip_circuit_breaker`.

## navigation_watchdog_seconds

Outer backstop `Crawl4AICrawler._run_with_watchdog` wraps around every
`arun()` call, independent of `page_timeout_seconds` above -
`page_timeout_seconds` only bounds crawl4ai's own internal navigation
clock once a navigation has actually started, so anything stuck *before*
that (a browser/session-management lock inside crawl4ai itself, for
example) is invisible to it entirely.

Confirmed live on austral.edu.ar: a scout-only sweep
(`docs/dev/spiders/orchestration/mechanical_loop/config.md#scout_only`)
deadlocked for 12+ minutes with `page_timeout_seconds` in effect the
whole time. A `py-spy dump` of the live process proved none of the
workers had even reached a graph-store write yet - the `ladybug-writer`
thread sat idle with nothing queued, and every `asyncio.to_thread` pool
worker showed only its bare dispatch-loop frame, nothing deeper into
`sink.py`. So the stall was somewhere inside crawl4ai/Playwright itself,
most plausibly a lock contested at a much higher rate under the scout
sweep - which removes the interaction pacing (click waits, extraction
delays) that had kept this from ever surfacing under the ordinary fused
`visit()` pass.

Default `60.0` - four times the default `page_timeout_seconds` (15.0),
mirroring the same "4x = something is wrong" ratio
`TargetLoadThrottle._SEVERE_SLOWDOWN_MULTIPLIER` already uses elsewhere
in this codebase - generous enough that a legitimately slow-but-alive
page (which crawl4ai's own `page_timeout_seconds` should already have
caught and converted to an ordinary failure well before this fires)
never trips it, but bounded enough that a genuine hang costs minutes,
not an unbounded wait.

Explicitly a partial fix, not a root-cause one: this codebase doesn't
control crawl4ai's own internals, so this can only bound *this
codebase's own* wait and recover the crawl - it can't fix whatever
actually wedged inside crawl4ai. See `_run_with_watchdog` below for the
best-effort session-cleanup attempt that goes with it.

## session_cleanup_timeout_seconds

Bounds `Crawl4AICrawler.close_session`'s own call into crawl4ai's
`kill_session` - a **second, distinct** deadlock site from the one
`navigation_watchdog_seconds` above guards, found the same way: a
scout-only sweep froze again, for 5+ minutes, well past
`navigation_watchdog_seconds`'s own 60s bound with no recovery. A live
`py-spy dump` proved the stall wasn't in `arun()` or the graph-store
writer - both were completely idle. The remaining, previously-unguarded
candidate: `MechanicalCrawler._recycle_session_if_due`
(`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_recycle_session_if_due`)
calls `close_session` every `session_recycle_after` visits, reaching the
exact same class of crawl4ai session/browser-management internals
`navigation_watchdog_seconds` already guards elsewhere - just through a
call path that bound never touched.

Default `10.0` - short, since closing an already-idle tab is normally
near-instant; no need for anything close to `navigation_watchdog_seconds`'s
own 60s scale here. See
`docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#close_session`
for the full reasoning and why this is bound once, at `close_session`
itself, rather than wrapped separately at each of its two callers.
