# `spiders/browser/dom_settle.py`

## module

Extracted from `crawl4ai_crawler.py` (previously module-level helpers in that
file): waiting for a live page to actually settle after a navigation or
interaction, before the caller runs discovery against it. Pure - takes a
Playwright `page` and a ceiling in seconds, touches no `Crawl4AICrawler`
state - which is what made it a clean pull-out once `crawl4ai_crawler.py`
tripped the `file-size-audit` skill's SPLIT tier (616 lines).

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

## _stable_hold_seconds

How long `_DOM_CHANGE_SIGNAL_JS` must go unchanged, after the last time
it *did* change, before `_wait_for_new_content` treats a page as
settled. 400ms, chosen with margin over the ~130ms intermediate-render
plateau live-measured on empanad.app (see `_wait_for_new_content`'s own
doc anchor below) - large enough to outlast a typical loading-state
blip, small enough to still return well before a multi-second
`ceiling_seconds` on a page that has nothing further to reveal.

## _wait_for_new_content

Replaces a flat `asyncio.sleep(ceiling_seconds)` with a short-step poll
that returns once `_DOM_CHANGE_SIGNAL_JS` (element count | body text
length | total class count, a cheap proxy - see that constant's own
doc anchor for why those three specifically) has changed at least once
*and then gone `_STABLE_HOLD_SECONDS` without changing again*, still
bounded by the same `ceiling_seconds` a flat sleep would have spent
regardless.

**A first attempt at this used plain DOM-stability (stop once the DOM
stops changing, with no baseline comparison at all) and was wrong** -
reverted after it broke both `test_wait_seconds_finds_content_
rendered_after_a_delay` and `test_interaction_wait_seconds_controls_
post_click_settle_delay`. `delayed_render.html`'s content arrives via a
one-shot `setTimeout`, not continuous mutation - the DOM is perfectly
static for the 1.5s *before* the timer fires, which looks identical to
"already settled" to a stability check with no baseline to compare
against. No amount of DOM-diffing can tell those two states apart
before the timer actually fires - this is a hard limit, not a tuning
problem. Kept as a lesson here since the same mistake is easy to
re-derive from a plain intent to "detect when the page is settled";
the current code sidesteps it by gating the stability check on
`changed_from_baseline` first - a still-static-since-navigation page
never reaches the stability check at all, it just keeps polling toward
the ceiling exactly like the original flat sleep would.

**Update (2026-08-11, the empanad.app "0 components after clicking
'Crear pedido'" bug) - returning on the *first* detected change was
itself a narrower version of the same mistake, just one step later in
the sequence:** a click that kicks off an async fetch-then-render flow
(an optimistic loading-state class toggle first, the real destination
content only after the network round-trip resolves) produces at least
two DOM changes in sequence, not one. The first fix attempt returned
the instant `changed_from_baseline` went true and stayed true for one
more poll step - which caught the loading-state toggle and never saw
the real content, confirmed on a real crawl via the debug log:
`on_execution_ended` fired ~800ms after the click (a couple of poll
steps, not the multi-second network round-trip this site's order flow
actually needs), and the resulting snapshot had 0 components with a
1-char markdown body - the pre-render shell, not the destination
screen.

**Update (2026-08-11, same day, second instance found by testing the
first fix directly against the live site instead of trusting the
fixture suite alone) - "one more poll step of quiet" was still too
short a confirmation window for this site's *real* timing:**
instrumenting `_wait_for_new_content` with a temporary per-poll log and
running it against `https://www.empanad.app/` directly (not a fixture)
showed the actual sequence: baseline at t=0, an intermediate change at
~0.24s (10 chars of body text - clearly a loading state, not the real
page), holding for **~0.13s**, then the real content (445 chars, the
site's 3 real components) at ~0.49s. One 0.1s poll step of quiet is
shorter than that 0.13s plateau, so the first fix's "stable" check
fired on the intermediate step and still returned 0 components against
the real site - passing every fixture-based test in the suite the
whole time, because the fixture built for the first fix baked its own
intermediate change into the *baseline itself* (a synchronous
`classList.add` inside the click handler, already applied by the time
`_wait_for_new_content` took its first reading) rather than genuinely
reproducing a change that happens *after* baseline capture, the way a
real async UI update does. The corrected fixture
(`two_stage_reveal_on_click.html`, rewritten the same day) applies its
loading-state toggle via `setTimeout(..., 50)` instead, so it lands
after baseline the way the real bug does.

The fix: track the timestamp of the *last* signal change (re-armed on
every change seen, not just the first) and require `_STABLE_HOLD_
SECONDS` of quiet since then, not a fixed one-poll-step confirmation.
This rides out a chain of any number of intermediate states - each new
change simply resets the clock - while still returning well before
`ceiling_seconds` once a page genuinely has nothing left to reveal (a
still-static-since-navigation page never even starts that clock, so it
falls through to the original flat-sleep-equivalent behavior exactly
as before). Verified directly against the live site post-fix: 3/3
components found consistently across repeated runs. See
`test_settle_wait_survives_a_short_plateau_before_the_real_change`
(`tests/test_crawl4ai_crawler.py`).

**How to catch this in review/testing**: a fixture that bakes its
"intermediate change" into a synchronous DOM mutation inside the same
event handler that triggers the interaction cannot catch a bug in how
*baseline itself* gets captured - by the time any wait-loop takes its
first reading, that mutation already happened. Any fixture built to
regression-test a settle-wait's handling of a multi-stage change must
apply its earlier-stage mutation asynchronously (its own short
`setTimeout`), so the wait function's baseline capture and the
mutation are genuinely racing the way a real click-triggered React
state update would.

A page whose signal never changes (a click that reveals nothing, or a
page with no delayed content at all) simply spends the full
`ceiling_seconds`, identical to the original flat-sleep behavior -
never worse, only faster when there's something to detect early.
Returns silently (no exception) on a torn-down execution context -
`page.evaluate` failing here almost always means a navigation happened
mid-poll, and the caller's own extraction (`run_extraction`, called
right after) is what actually needs to react to that, not this check.

## _wait_for_new_content-navigation

A page that navigates mid-wait destroys the JS context, and reading the
DOM signal raises. That used to `return` with the comment "let the
caller's own extraction handle it" - and the caller has no way to know the
page moved underneath it, so discovery read the old document.

The wait now recognises a redirect for what it is: the new page *is* what
it was waiting for. It restarts on that document with a fresh budget,
because the new page has only just begun and inheriting the spent
remainder would leave it no room to render.

Bounded by `_NAVIGATION_RESTARTS`. A redirect chain is real - a landing
page bouncing through auth and then into the app - but an unbounded one is
a trap, and each restart costs a whole ceiling.

Only a genuine navigation error restarts (`_is_navigation_context_error`).
Any other failure still returns at once: a dead page must not consume the
budget.

## the timeline this was measured against

Sampled live on empanad.app every 300 ms, which is what settled the
design:

| t | nodes | controls | url |
|---|---|---|---|
| 0.3s | 35 | 0 | `/` |
| 0.6s | 35 | 0 | `/` — quiet, empty |
| 0.9s | 36 | 0 | `/o/{token}` — redirected |
| 1.3s | 36 | 0 | `/o/{token}` — quiet again, still empty |
| 1.6s | 61 | 3 | `/o/{token}` — controls at last |

**Two** plateaus where the DOM is quiet and has nothing on it, either of
which satisfies the settle heuristic. That is why the redirect fix alone
only halved the failures: with `wait_seconds: 1.0`, a restart at 0.9s
gives a deadline of ~1.9s, and the 1.6s render plus 0.4s of required quiet
lands at ~2.0s - just outside.

## _dom_change_signal_js

A cheap proxy for "did the DOM change", polled by `_wait_for_new_content`
instead of the full discovery pass - that one forces a `getComputedStyle()` per
element and is far too expensive to run ~20x per interaction just to ask whether
anything moved.

**Node count alone is not enough**, and this is live-verified rather than
reasoned: on a site where an interaction toggles a class (an active filter chip)
or updates text (a results count) without adding or removing any element, node
count sees nothing. 35 of 39 interactions on one real site were that shape.
