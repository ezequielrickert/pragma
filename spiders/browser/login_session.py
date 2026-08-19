"""Login-session file management and the headed capture flow itself.

Deliberately has no opinion on *when* a session should be captured (see
`spiders/browser/login.py` for that orchestration) - this module only
answers "where does site X's session live", "is the file at this path
still good", "does this page even need one", and "go capture one".
Details: docs/dev/spiders/browser/login_session.md#module
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

# Case-insensitive substrings that mark a button/link as a login trigger -
# English and Spanish (the project's other real target sites are
# Spanish-language), covering the common phrasings without trying to be
# exhaustive; see find_login_trigger for what this is used for.
# Details: docs/dev/spiders/browser/login_session.md#_LOGIN_TRIGGER_KEYWORDS
_LOGIN_TRIGGER_KEYWORDS = (
    "log in", "login", "sign in", "signin",
    "iniciar sesión", "iniciar sesion", "acceder", "ingresar",
)


def session_path(site: str, sessions_dir: str = "data/sessions") -> str:
    """Where `site`'s captured storage_state lives, whether or not it
    exists yet. Details: docs/dev/spiders/browser/login_session.md#session_path
    """
    return os.path.join(sessions_dir, f"{site}.json")


def is_session_valid(path: str, max_age_hours: float) -> bool:
    """True when `path` exists and is younger than `max_age_hours`.

    A missing or stale session must never be handed to the real crawl as
    if it were still good - an expired cookie fails the crawl silently
    (pages just render logged-out) rather than raising, so staleness has
    to be caught here, before that crawl ever starts.
    Details: docs/dev/spiders/browser/login_session.md#is_session_valid
    """
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours <= max_age_hours


def has_login_form(components: List[Dict[str, Any]]) -> bool:
    """True when any discovered component is a password input.

    The one reliable signal across arbitrary sites - label text, form
    action, and button copy ("Sign in" vs "Log in" vs "Access account")
    vary too much to pattern-match, but a `<input type="password">` means
    a login gate regardless of how the surrounding page phrases it.
    Details: docs/dev/spiders/browser/login_session.md#has_login_form
    """
    return any(
        c.get("tag") == "input" and c.get("input_type") == "password"
        for c in components
    )


def find_login_trigger(components: List[Dict[str, Any]]) -> Optional[str]:
    """CSS path of a button/link whose visible text reads like a login
    trigger (e.g. "Iniciar Sesión", "Log in"), or `None`.

    `has_login_form` alone misses a real, common case: a site (e.g. a
    React/Vue SPA) that mounts its password field only after this kind
    of element is clicked - a modal, an inline form swap - so nothing
    resembling a login form exists in the page as first loaded. This is
    the one extra hop `ensure_login_session` takes before concluding a
    page has no login gate at all.
    Details: docs/dev/spiders/browser/login_session.md#find_login_trigger
    """
    for c in components:
        if c.get("tag") not in ("button", "a"):
            continue
        text = (c.get("text") or "").strip().lower()
        if any(keyword in text for keyword in _LOGIN_TRIGGER_KEYWORDS):
            return c.get("path")
    return None


async def capture_login_session(url: str, save_path: str, *, headless: bool = False) -> None:
    """Open a real, headed browser at `url`, let a human sign in by hand,
    then persist the resulting cookies/localStorage to `save_path`.

    Blocks on stdin via `asyncio.to_thread` rather than a bare `input()`
    call, so this coroutine's event loop keeps servicing the browser (and
    anything else running alongside it) while a human is off in a
    separate window typing a password.
    Details: docs/dev/spiders/browser/login_session.md#capture_login_session
    """
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)
        print(f"Opened {url} in a browser window - sign in, then return here.")
        await asyncio.to_thread(input, "Press Enter once you're logged in: ")
        await context.storage_state(path=save_path)
        await browser.close()
    print(f"Login session saved to {save_path}")
