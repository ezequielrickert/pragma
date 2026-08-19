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
from .login_session import capture_login_session, has_login_form, is_session_valid, session_path


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
    visits `url` once to check for a login form; a form found there
    triggers the headed capture flow before the caller's own crawl ever
    starts. A page with no login form costs nothing beyond that one
    precheck visit.
    Details: docs/dev/spiders/browser/login.md#ensure_login_session
    """
    candidate = session_path(site, sessions_dir)
    if is_session_valid(candidate, max_age_hours):
        print(f"Reusing cached login session for {site}")
        return candidate

    precheck_config = Crawl4AICrawlerConfig(headless=headless)
    async with Crawl4AICrawler(precheck_config) as precheck:
        page_state = await precheck.discover_page(url)
    if not has_login_form(page_state.components):
        return None

    await capture_login_session(url, candidate, headless=headless)
    return candidate


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
