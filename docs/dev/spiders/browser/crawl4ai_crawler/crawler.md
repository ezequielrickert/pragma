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
session instead; `discover_pages_many()` is a third, independent shape -
see its own section below.

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

## discover_pages_many

Navigate to every url in a batch concurrently via crawl4ai's own
`arun_many()` + `MemoryAdaptiveDispatcher`, instead of this crawler's own
per-navigation `TargetLoadThrottle` loop. Built specifically for
`measurement_pass.py`'s shape - many independent, already-known URLs, no
interaction, no session reused across calls - which is exactly what
`arun_many()` is designed for; `discover_page`/`click`/`fill`'s shape
(one URL, many sequential `arun()` calls against the same session, each
depending on the last) has no equivalent in `arun_many()`, so that path
keeps its own throttle rather than trying to fit this one.

Each URL gets its own `CrawlerRunConfig(session_id=url, ...)`, matching
`discover_page`'s own `session_id = session_id or url` default so
`before_retrieve_html`'s stash write never collides across concurrently-
running pages.

## discover_pages_many-url_matcher

**`url_matcher` is required, not optional, on every one of those configs.**
Found the hard way: `arun_many()`'s dispatcher resolves which config
belongs to which URL via `CrawlerRunConfig.is_match(url)`, and a config
with no `url_matcher` matches *every* URL unconditionally (see
`crawl4ai`'s own `async_dispatcher.py::select_config`, which returns the
first config where `is_match()` is true). Without setting one, every
concurrently-dispatched URL silently resolved to `configs[0]`'s
`session_id` - live-verified with two distinct fixture pages, where both
pages' hook invocations reported the *same* `session_id`, and the second
page's real extraction was lost entirely (its stash entry was just
overwritten by the first page's data, read back as an empty
`components: []`). Each config now sets
`url_matcher=lambda candidate, target=url: candidate == target`, closing
over `url` by value via the default argument (not the loop variable by
reference, which would have every lambda close over the same final
`url`). `tests/test_crawl4ai_crawler.py::test_discover_pages_many_returns_a_page_state_per_url_in_order`
pins this regression.

Returns `(url, PageState)` per successful page and `(url, None)` for a
page that failed to load or timed out - the batch's own tolerant
contract, not `discover_page`'s raise-on-failure one, so one bad page in
the batch doesn't cost the rest (mirrored by
`test_discover_pages_many_reports_a_failed_page_as_none_without_costing_the_rest`,
which forces a real timeout via a slow fixture endpoint alongside a
normal one).

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
