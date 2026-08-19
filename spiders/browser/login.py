"""Login orchestration: the decision of *when* to capture a session,
decoupled from any one caller.

This is the auto-invoke hook contract - `ensure_login_session` is what a
crawl stage (`pragma static`, `pragma dynamic`) calls before it opens its
own real browser, instead of crashing on a login wall or re-deriving this
same reuse-cache/precheck/capture decision itself. It depends only on
`Crawl4AICrawler` for the precheck navigation, never on `Engine` or any
other orchestrator - the coupling that made the previous login attempt
hard to reuse from more than one call site.
Details: docs/dev/spiders/browser/login.md#module
"""
from __future__ import annotations

from typing import Optional

from .crawl4ai_crawler.config import Crawl4AICrawlerConfig
from .crawl4ai_crawler.crawler import Crawl4AICrawler
from .login_session import (
    capture_login_session,
    find_login_trigger,
    has_login_form,
    is_session_valid,
    session_path,
)


async def ensure_login_session(
    url: str,
    site: str,
    *,
    sessions_dir: str = "data/sessions",
    max_age_hours: float = 24.0,
    headless: bool = False,
) -> Optional[str]:
    """Storage-state path a real crawl of `url` should launch with, or
    `None` for an anonymous crawl.

    A valid cached session for `site` is used directly - no browser
    opened, no extra navigation. Otherwise a throwaway `Crawl4AICrawler`
    visits `url` once to check for a login form. Many sites (React/Vue
    SPAs especially) mount their password field only after a "Log in"/
    "Iniciar Sesión"-style button is clicked - nothing resembling a form
    exists on the page as first loaded - so a page with no login form
    yet gets one more chance: if `find_login_trigger` spots such a
    button/link, the precheck clicks it and checks again before giving
    up. A form found either way triggers the headed capture flow before
    the caller's own crawl ever starts. A page with no login form and no
    trigger costs nothing beyond that one precheck visit. A trigger that
    was clicked but still didn't surface a password field (a multi-step
    flow this precheck isn't meant to chase) prints a pointer at
    `pragma login` instead of silently crawling anonymous - that failure
    mode is otherwise indistinguishable from "this site has no login at
    all".
    Details: docs/dev/spiders/browser/login.md#ensure_login_session
    """
    candidate = session_path(site, sessions_dir)
    if is_session_valid(candidate, max_age_hours):
        print(f"Reusing cached login session for {site}")
        return candidate

    precheck_config = Crawl4AICrawlerConfig(headless=headless)
    clicked_a_trigger = False
    async with Crawl4AICrawler(precheck_config) as precheck:
        page_state = await precheck.discover_page(url, session_id=url)
        if not has_login_form(page_state.components):
            page_state, clicked_a_trigger = await _click_login_trigger_if_any(precheck, url, page_state)
    if has_login_form(page_state.components):
        await capture_login_session(url, candidate, headless=headless)
        return candidate

    if clicked_a_trigger:
        # Found and clicked something that read like a login trigger, but
        # still no password field - most likely a multi-step flow (an
        # OAuth/email choice screen, a second click) this precheck isn't
        # meant to chase. Silently crawling anonymous here would look
        # identical to "this site genuinely has no login", which it isn't.
        print(
            f"Found a login trigger on {url}, but no password field appeared after clicking it - "
            f"this site's login flow needs more than one step. Run `pragma login {url}` to sign in "
            "by hand once; every later run will reuse the cached session."
        )
    return None


async def _click_login_trigger_if_any(precheck: Crawl4AICrawler, url: str, page_state):
    """One extra click, if `page_state` has a plausible login trigger and
    nothing resembling a login form yet - see `ensure_login_session` for
    why. Returns `(post_click_page_state, True)` when a trigger was
    clicked, or `(page_state, False)` unchanged when there was nothing to
    click - the caller uses that flag to tell "no login gate at all"
    apart from "found one, couldn't finish it automatically". A click
    that fails outright (the element vanished, an unrelated error) is
    treated the same as "no trigger found" - this is a best-effort
    second look, not something the caller should ever crash over.
    Details: docs/dev/spiders/browser/login.md#_click_login_trigger_if_any
    """
    trigger_path = find_login_trigger(page_state.components)
    if trigger_path is None:
        return page_state, False
    try:
        return await precheck.click(url, url, trigger_path), True
    except Exception as exc:
        print(f"Warning: could not click login trigger while checking {url!r}: {exc}")
        return page_state, False


async def force_login_session(
    url: str,
    site: str,
    *,
    sessions_dir: str = "data/sessions",
    headless: bool = False,
) -> str:
    """Always captures a fresh session, regardless of a still-valid cached
    one - the standalone `pragma login` command's entry point. A human
    running that command by hand is explicitly asking to sign in, so it
    skips both the reuse check and the login-form precheck that
    `ensure_login_session` uses to stay quiet on pages that don't need it.
    Details: docs/dev/spiders/browser/login.md#force_login_session
    """
    candidate = session_path(site, sessions_dir)
    await capture_login_session(url, candidate, headless=headless)
    return candidate
