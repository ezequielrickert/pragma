"""`python3 src/cli.py login <url>` - saves a logged-in browser session for reuse.
Details: docs/dev/core/login_helper.md#module
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright


def run_login_helper(url: str, storage_state_path: str) -> None:
    """Open `url` visibly, wait for the user to log in, save the session state.
    Details: docs/dev/core/login_helper.md#run_login_helper
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
