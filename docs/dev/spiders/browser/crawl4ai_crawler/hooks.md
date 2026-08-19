# `spiders/browser/crawl4ai_crawler/hooks.py`

## module

Every crawl4ai hook callback this project registers, plus the
`session_id -> extraction dict` stash they read/write. Composed by
`Crawl4AICrawler` (`self._hooks = HookHandlers(config)`), not inherited -
this collaborator has its own reason to change (crawl4ai's hook contract,
extraction-retry policy) independent of `Crawl4AICrawler`'s own (the
public navigate/interact API) - see the `clean-code-principles` skill's
`core-composition` rule for the general principle this follows.

Confirmed via a spike against a local fixture server, from back when this
logic still lived inline in `crawl4ai_crawler.py` (recorded in the
original migration plan file's "Phase 0 spike" section):
- `before_retrieve_html` fires after `wait_for` but *before* any
  `js_code` on the same `arun()` call executes - correct for a
  plain-navigation discovery pass, but NOT correct for re-discovering
  after a scripted interaction (see `on_execution_ended` below).
- `on_execution_ended` fires immediately after `js_code` runs - the hook
  a post-click/fill re-discovery must use instead.
- A hook is a plain `async def` callable with no return channel back
  into `arun()`'s result, so discovery output is stashed in `self._stash`,
  keyed by `session_id`, and read back by `Crawl4AICrawler` via `pop()`
  after `arun()` returns.

**Update - the original spike correctly picked which hook's *data* to
trust for each case, but missed that `before_retrieve_html` still *runs*
on the other one too:** confirmed live on austral.edu.ar - a real crawl's
own debug log showed 198 `before_retrieve_html` events for 12 distinct
pages actually visited. Reading crawl4ai's source
(`async_crawler_strategy.py`) directly shows why:
`execute_hook("before_retrieve_html", ...)` is called **unconditionally
on every single `arun()` call**, `js_only` or not - there is no gate
around it the way `on_execution_ended`'s call *is* correctly wrapped in
`if config.js_code:`. So every `click`/`fill`/`resync`/`go_back`
(`_interact`, `js_only=True`) was *also* running
`before_retrieve_html`'s full body - before `js_code` had even executed,
so `_wait_for_new_content` could never observe a change and burned its
entire `wait_seconds` ceiling every time, on top of
`on_execution_ended`'s own, correct wait afterward. A real, systemic ~2s
tax on every interaction across the whole crawl - not a one-off cost, and
easy to misread as "the page got re-fetched" from crawl4ai's own
per-`arun()` `[FETCH]/[SCRAPE]/[COMPLETE]` console reporting, which fires
identically for a `js_only` call. Fixed by gating the hook's own body on
`config.js_only` - see `before_retrieve_html-js-only-skip` below.

## _action_mark

A window property used to hand a click/fill's own success/failure back
to Python - crawl4ai's `robust_execute_user_script` logs-and-continues on
a `js_code` error rather than failing the `arun()` call (confirmed by
reading `async_crawler_strategy.py`), which would otherwise repeat the
exact swallowed-failure bug wiki/browser-automation-pitfalls.md documents
for `PlaywrightScraper.click()`'s old bare try/except. `Crawl4AICrawler`'s
`click()`/`fill()`/`resync()` wrap their own JS in a try/catch that writes
here; `on_execution_ended` below reads it back explicitly - what makes a
real action failure raise instead of silently looking like a no-op.

## _blocked_resource_types

Resource types genuinely safe to drop for component discovery/interaction
purposes when `block_images` is enabled - never "stylesheet" (layout
affects visibility/rect discovery), never "script"/"xhr"/"fetch"/
"document" (would break the SPA itself). Real bandwidth/time savings,
unlike crawl4ai's own `exclude_external_images` - see
`docs/dev/spiders/browser/crawl4ai_crawler/config.md`'s `block_images`
entry for why that flag doesn't touch the network layer at all.

## HookHandlers

Owns the `session_id -> extraction dict` stash and every crawl4ai hook
callback that reads or writes it.

## _stash

Populated by whichever hook last ran for a given `session_id` -
`before_retrieve_html` after a plain navigation, `on_execution_ended`
after a scripted interaction. Consumed via `pop()`, not read directly, so
callers never see a stale entry from a previous call against the same
session reused across it.

## pop

Consume and return `session_id`'s stashed extraction, or `{}` if nothing
was ever stashed for it (a navigation/interaction that failed before its
hook ran).

## log_only_hook

Build a hook callback that only logs to `self.debug_log`, for the
crawl4ai hooks this class has no functional use for
(`on_browser_created`/`on_page_context_created`/`on_user_agent_updated`/
`on_execution_started`/`before_goto`/`after_goto`/`before_return_html`)
but the user wants a debug record of anyway - "every event that triggers
a hook" should show up in `debug.md`, not just the two this class already
reads discovery data from. See `docs/dev/spiders/browser/debug_log.md#log_hook_from_raw`
/`#loggable_hook_details` for which fact each hook type actually carries.

The inner `hook(*args, **kwargs)` closure is a plain sync callable, not
`async def` - crawl4ai's `execute_hook` checks
`asyncio.iscoroutinefunction()` and calls either way, and this does no
awaiting of its own, just formatting + a synchronous file write via
`self.debug_log`.

## on_page_context_created

Registered unconditionally by `Crawl4AICrawler.__aenter__` (see
`docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#__aenter__-single-slot-hooks`)
- installs `block_images`'s route handler when enabled, and folds in the
same log-only behavior `log_only_hook` would otherwise provide for this
hook when `debug_log` is set (crawl4ai allows only one callback per hook
name).

Fires on *every* `arun()` call for a session, not just when a new page is
actually created (confirmed by reading `async_crawler_strategy.py`: this
hook runs unconditionally right after `browser_manager.get_page()`,
whether that returned a fresh page or a cached, reused one) - so the
route handler is guarded by a flag stashed directly on the `page` object,
the same "don't double-inject" pattern crawl4ai's own
navigator-overrider/shadow-DOM hooks already use on `context`, to avoid
stacking a duplicate `page.route()` handler on every single interaction
against an already-routed, reused page.

## on_page_context_created-timeout

Changes what Playwright's *own* internal waits (e.g.
`robust_execute_user_script`'s un-timed
`wait_for_load_state("domcontentloaded")`) fall back to when they carry
no explicit timeout of their own - see
`docs/dev/spiders/browser/crawl4ai_crawler/config.md`'s
`interaction_timeout_seconds` entry for the exact failure this fixes.
Safe to call on every `arun()` (no "already installed" guard needed,
unlike the route handler above - this is a plain property set, not a
stacking handler).

## _retry_empty_extraction

Zero components **and** zero links on a page with a real DOM is almost
never a true description of that page. It is the settle-wait having
returned on an intermediate render - the same failure `_STABLE_HOLD_SECONDS`
exists for, on an application whose plateau outlasts that 0.4s window.

**The failure it was written from.** A real crawl of empanad.app logged
`before_retrieve_html` with `components: 0, links: 0` against
`html_length: 21891`, and the whole run produced one page node, no
components, and documents that all rendered empty. Nothing errored: the
crawl accepted "this page has nothing on it" as a finding.

Exactly one extra attempt, on **any** empty extraction. An earlier version
gated it on the page having at least 50 elements, which sounds prudent and
skipped precisely the case it was written for - see
`docs/dev/spiders/browser/dom_settle.md` for the timing table this refers
to. A "is this page substantial" threshold cannot tell a redirecting
shell from a stub, because they are the same size.

A page that genuinely has no controls and no links - a legal notice, an
error page - stays empty rather than being retried into existence, and
pays one extra settle-wait for it. That is the whole cost, and it buys
the case that matters.

Only on the plain-navigation path (`before_retrieve_html`), not after a
scripted click: an interaction that reveals nothing is an ordinary
outcome, not a symptom.

## before_retrieve_html

Discovery point for a plain navigation pass - see the `module` section
above for why this hook is specifically wrong for a post-interaction
re-discovery, and why it has to actively skip itself for one rather than
just being the wrong *data source* for it.

## before_retrieve_html-js-only-skip

`config.js_only` (set only by `_interact`, never by `discover_page`) is
what this hook's own early-return actually gates on - not the hook firing
itself, which crawl4ai fires unconditionally regardless (see the
`module` section's "Update" note). Skips the settle-wait, extraction,
`_retry_empty_extraction`, stash write, and debug log entirely for a
`js_only` call: `on_execution_ended` already does the correct version of
all of that, after `js_code` has actually run, and nothing ever reads
this hook's stash write for a `js_only` call before `on_execution_ended`
overwrites it moments later within the same `arun()` call.

## on_execution_ended

Discovery point for the interaction-followup case: fires immediately
after `config.js_code` runs, so it sees post-interaction DOM state. Also
reads back `_ACTION_MARK` (see `_action_mark` above) so
`Crawl4AICrawler.click()`/`fill()` can tell a real failure from a
successful no-op, instead of trusting crawl4ai's own swallow-and-log
behavior for a failed `js_code` execution.

A click/fill that itself triggers real navigation (a plain `<a href>`, or
an onclick that sets `location`) destroys the JS execution context
**synchronously, mid-statement** - confirmed empirically: `click()`/
`fill()`'s own JS is a single IIFE that calls `el.click()` and *then*
assigns `_ACTION_MARK` on the next line, but for a navigating click, the
browser starts unloading the page the moment `el.click()` runs, so the
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
method reads `_ACTION_MARK` first (the precise success/failure the
click/fill JS explicitly set, for the common non-navigating case) and
only falls back to `result` when the marker comes back unset - which, per
the above, means a navigation pre-empted it, not that the action silently
did nothing. Treating a missing marker as an unconditional failure (an
earlier version of this method did exactly that) was actively dangerous:
the caller then believed the click was a no-op and kept issuing further
clicks/fills from the *same* pass, each evaluated against selectors that
belonged to a page no longer there - confirmed to cascade into "element
not found" errors on every subsequent component in that pass, not just
the one that actually navigated.

## on_execution_ended-navigation-retry

crawl4ai's own `robust_execute_user_script` already waits out a
navigation before this hook fires (see `on_execution_ended` above), but
if discovery still races ahead of it in some edge case, give the new page
one more chance to settle before retrying extraction.

## on_execution_ended-fallback

`marked is False`: evaluate itself failed for a reason other than a
navigation tearing down the context - a genuine, otherwise-unexplained
failure to even read the marker back.

Marker was never set (`None`, or evaluate raised the
navigation-destroyed error): fall back to crawl4ai's own execution
result, which already resolved whether this was a real navigation.
