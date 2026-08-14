"""Wait for a live page to actually settle after a navigation or interaction.
Details: docs/dev/spiders/browser/dom_settle.md#module
"""
from __future__ import annotations

import asyncio
from typing import Optional

# How many times _wait_for_new_content will start over because the page
# navigated under it. A redirect chain is real (a landing page bouncing
# through auth, then to the app); an unbounded one is a trap, and each
# restart costs a full ceiling.
# Details: docs/dev/spiders/browser/dom_settle.md#_wait_for_new_content
_NAVIGATION_RESTARTS = 3

# _wait_for_new_content's poll step.
# Details: docs/dev/spiders/browser/dom_settle.md#_adaptive_wait_step_seconds
_ADAPTIVE_WAIT_STEP_SECONDS = 0.1

# How long the DOM-change signal must hold steady, after it first differs
# from where it started, before _wait_for_new_content treats it as settled.
# Live-verified against a real crawl of empanad.app (2026-08-11): after
# clicking into the order flow, the signal changes once at ~0.24s (a false,
# intermediate render step - 10 chars of body text, clearly a loading
# state) and holds there for only ~0.13s before the real destination
# content appears at ~0.49s (445 chars of body text, the actual 3
# components). A single 0.1s poll step of "stability" (this function's
# first version) is shorter than that ~0.13s plateau, so it returned on the
# fake intermediate step - this margin is chosen to comfortably outlast it.
# Details: docs/dev/spiders/browser/dom_settle.md#_stable_hold_seconds
_STABLE_HOLD_SECONDS = 0.4

# Cheap proxy for "did the DOM change", polled by _wait_for_new_content instead
# of the full DISCOVER_COMPONENTS_JS pass (which forces a getComputedStyle()
# per element and is far too expensive to run ~20x per interaction just to
# check whether anything changed). Node count alone missed real changes on
# sites where an interaction toggles a class (active filter chip) or updates
# text (a results count) without adding/removing any element - live-verified
# against mapadeprofesionales.com, where 35 of 39 interactions always slept
# the full ceiling instead of returning early. Text length and total class
# count are just as cheap (one pass, no getComputedStyle) and catch both.
# Details: docs/dev/spiders/browser/dom_settle.md#_dom_change_signal_js
_DOM_CHANGE_SIGNAL_JS = """() => {
    const all = document.querySelectorAll('*');
    let classCount = 0;
    for (const el of all) classCount += el.classList.length;
    return all.length + '|' + document.body.textContent.length + '|' + classCount;
}"""


def _is_navigation_context_error(exc: Exception) -> bool:
    """Whether `exc` is Playwright's "JS execution context was torn down" error.
    Details: docs/dev/spiders/browser/dom_settle.md#_is_navigation_context_error
    """
    msg = str(exc).lower()
    return "context was destroyed" in msg and "navigation" in msg


async def _wait_for_new_content(page, ceiling_seconds: float) -> None:
    """Poll a cheap DOM-change signal in short steps, returning once it has
    changed at least once AND held steady for `_STABLE_HOLD_SECONDS` -
    not on the first sign of change, and not after just one poll step of
    quiet either.
    An async fetch-then-render flow (click a submit button -> optimistic
    loading state -> network round-trip -> real content swaps in) produces
    at least two DOM changes in sequence, not one, and the *first* one can
    itself plateau just long enough to look settled before the real one
    arrives - live-verified on empanad.app (2026-08-11): after clicking
    into the order flow, an intermediate loading-state render held steady
    for ~0.13s before the real destination content (445 chars of body
    text, the actual components) appeared. A version of this function that
    required only one poll step (0.1s) of post-change quiet returned right
    on that intermediate plateau - shorter than the plateau itself - and
    persisted 0 components. `last_change_time` is re-armed on *every*
    change seen, not just the first, so a longer chain of intermediate
    states is ridden out the same way a single one is; the fixed hold
    window is what makes "quiet" mean "actually done," not merely
    "unchanged for one sample."
    A page that *navigates* mid-wait - a landing page redirecting to the
    real application - destroys the JS context, and reading the signal
    raises. That used to return immediately and hand the caller a page in
    the middle of moving; discovery then read the old, empty document.
    Now the wait treats it for what it is - a new page, which is the
    thing it was waiting for - and starts over on it with a fresh budget.
    Details: docs/dev/spiders/browser/dom_settle.md#_wait_for_new_content
    """
    if ceiling_seconds <= 0:
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ceiling_seconds
    restarts_left = _NAVIGATION_RESTARTS
    last_signal: Optional[str] = None
    last_change_time: Optional[float] = None

    while loop.time() < deadline:
        try:
            signal = await page.evaluate(_DOM_CHANGE_SIGNAL_JS)
        except Exception as exc:
            if not _is_navigation_context_error(exc) or restarts_left <= 0:
                return  # genuinely dead page, or a redirect chain past its budget
            # The page moved. Wait out the new document instead of handing
            # the caller a half-navigated one.
            restarts_left -= 1
            deadline = loop.time() + ceiling_seconds
            last_signal, last_change_time = None, None
            await asyncio.sleep(_ADAPTIVE_WAIT_STEP_SECONDS)
            continue

        now = loop.time()
        if last_signal is None:
            last_signal = signal  # first read of this document - nothing to compare yet
        elif signal != last_signal:
            last_change_time = now  # re-armed on every change, not just the first
            last_signal = signal
        elif last_change_time is not None and now - last_change_time >= _STABLE_HOLD_SECONDS:
            return  # changed at least once, quiet for the full hold window since
        await asyncio.sleep(_ADAPTIVE_WAIT_STEP_SECONDS)
