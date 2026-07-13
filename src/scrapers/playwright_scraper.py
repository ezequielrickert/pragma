"""
Playwright-based stateful scraper for Pragma with high-fidelity discovery.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, ElementHandle

from ..core.interfaces import PageState, Scraper
from ..core.registry import SCRAPER_REGISTRY


@SCRAPER_REGISTRY.register("playwright")
class PlaywrightScraper(Scraper):
    """A high-fidelity scraper that maintains a browser session."""

    def __init__(self, headless: bool = True, wait_seconds: float = 15.0) -> None:
        """Initialize scraper settings.

        Args:
            headless: Run the browser without a visible UI.
            wait_seconds: Extra time to let the page settle after navigation
                before reading links/components - JS-heavy nav (mega menus,
                client-rendered content) can otherwise still be missing from
                the DOM at extraction time. Raise this for slow/JS-heavy sites.
        """
        self.headless = headless
        self.wait_seconds = wait_seconds
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_browser(self) -> None:
        """Lazily start playwright and browser."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()

    def navigate(self, url: str) -> PageState:
        """Navigate to a URL and capture deep state."""
        self._ensure_browser()
        self._page.goto(url, wait_until="networkidle")
        time.sleep(self.wait_seconds)
        return self.get_state()

    def click(self, selector: str) -> PageState:
        """Click an element and capture new deep state.

        A click failure (bad/ambiguous selector, element not clickable, etc.)
        propagates so the caller can tell the click didn't happen - swallowing
        it here used to make every failed click look like a successful no-op,
        which was indistinguishable from a click that legitimately changed
        nothing. Only the post-click networkidle wait is treated as best-effort,
        since pages with persistent polling/analytics often never go idle.

        A normal click that times out specifically because the element isn't
        visible (common for dropdown/submenu items that only render on hover
        of a parent, but are present in the DOM the whole time) is retried
        with force=True, which dispatches the click directly and skips
        Playwright's visibility/actionability checks.
        """
        self._ensure_browser()
        try:
            self._page.click(selector, timeout=5000)
        except Exception as exc:
            if "not visible" not in str(exc):
                raise
            print(f"Element not visible, retrying with a forced click: {selector}")
            self._page.click(selector, timeout=5000, force=True)

        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: page did not reach idle after clicking {selector}: {exc}")

        time.sleep(self.wait_seconds)
        return self.get_state()

    def get_state(self) -> PageState:
        """Extract current page structure and interactive DNA."""
        self._ensure_browser()
        return PageState(
            url=self._page.url,
            title=self._page.title(),
            metadata=self._extract_metadata(),
            components=self._discover_components(),
            links=self._extract_links(),
        )

    def _extract_metadata(self) -> Dict[str, str]:
        """Extract meta tags and semantic markers."""
        script = """() => {
            const meta = {};
            document.querySelectorAll('meta').forEach(m => {
                const name = m.getAttribute('name') || m.getAttribute('property');
                if (name) meta[name] = m.getAttribute('content');
            });
            return meta;
        }"""
        return self._page.evaluate(script)

    def _discover_components(self) -> List[Dict[str, Any]]:
        """Perform deep discovery of all interactive components.

        Paths are built as valid, unique CSS selectors: an element with an id
        uses `tag#id`; otherwise it gets a `:nth-of-type(n)` index among its
        same-tag siblings. Without this, sibling elements with no id (e.g. every
        link in a nav menu) produce identical path strings, which then fail as
        CSS selectors with a Playwright "strict mode: resolved to N elements"
        error on click - silently, since click() only logs such failures.
        """
        script = """() => {
            const gp = (e, p=[]) => {
                while (e.parentElement) {
                    let seg = e.tagName.toLowerCase();
                    if (e.id) {
                        seg += '#' + e.id;
                    } else {
                        const siblings = Array.from(e.parentElement.children)
                            .filter(c => c.tagName === e.tagName);
                        if (siblings.length > 1) {
                            seg += ':nth-of-type(' + (siblings.indexOf(e) + 1) + ')';
                        }
                    }
                    p.unshift(seg);
                    e = e.parentElement;
                }
                return p.join(' > ');
            };
            return Array.from(document.querySelectorAll('button, a, input, select, textarea, [role="button"]'))
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    text: el.innerText.trim() || el.getAttribute('aria-label') || '',
                    path: gp(el),
                    attributes: { id: el.id, class: el.className, href: el.getAttribute('href') || '' }
                }));
        }"""
        return self._page.evaluate(script)

    def _extract_links(self) -> List[Dict[str, str]]:
        """Gather all unique, relevant hrefs and their labels."""
        script = """() => {
            return Array.from(document.querySelectorAll('a'))
                .filter(a => a.href && a.href.startsWith('http'))
                .map(a => ({
                    href: a.href,
                    text: a.innerText.trim() || a.innerHTML.trim()
                }));
        }"""
        return self._page.evaluate(script)

    def close(self) -> None:
        """Shutdown browser and playwright."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
