"""`python3 src/cli.py login <url>` - a one-time, interactive helper that opens a
real, visible browser, lets the user log in by hand, and saves the resulting
session (cookies + localStorage) to a Playwright storage-state JSON file that
`PlaywrightScraper.storage_state_path` can load on later runs.

Exists because there is no other easy way to produce that file: Playwright's
storage-state format isn't something a user could reasonably hand-write, and
Pragma's own crawl runs always launch a brand-new, empty, logged-out browser
(a separate process entirely from whatever the user is logged into in their own
regular browser - see docs/explicativos/playwright.md) - logging in "beforehand"
in a normal browser has no effect on it. This command is the bridge between the
two: log in once here, reuse the saved session on every crawl afterward.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright


def run_login_helper(url: str, storage_state_path: str) -> None:
    """Open `url` in a visible Chromium window, block on a terminal prompt until
    the user confirms they've finished logging in, then save the browser
    context's storage state to `storage_state_path`.

    Deliberately a plain blocking `input()`, not a timeout or a "wait for
    navigation" heuristic - a real login can involve multiple steps (password,
    2FA, a redirect back to the original page) with no single reliable signal
    that it's "done"; the user pressing Enter is unambiguous and doesn't force
    an arbitrary time limit on a slow 2FA flow.
    """
    print(f"Opening {url} in a browser window - log in there, then come back to this terminal.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        input("Press Enter here once you're logged in (leave the browser window open)... ")
        context.storage_state(path=storage_state_path)
        browser.close()
    print(
        f"Session saved to {storage_state_path}. Use --storage-state {storage_state_path} "
        f"(or storage_state_path: {storage_state_path} in pragma.yaml) on future runs to reuse it."
    )
