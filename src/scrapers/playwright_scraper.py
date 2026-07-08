"""
Playwright-based stateful scraper for Pragma with high-fidelity discovery.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, ElementHandle

from ..interfaces import Scraper


class PlaywrightScraper(Scraper):
    """A high-fidelity scraper that maintains a browser session."""

    def __init__(self, headless: bool = True) -> None:
        """Initialize scraper settings."""
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_browser(self) -> None:
        """Lazily start playwright and browser."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._page = self._browser.new_page()

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL and capture deep state."""
        self._ensure_browser()
        self._page.goto(url, wait_until="networkidle")
        time.sleep(1)
        return self.get_state()

    def click(self, selector: str) -> Dict[str, Any]:
        """Click an element and capture new deep state."""
        self._ensure_browser()
        try:
            self._page.click(selector, timeout=5000)
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: Interaction failed on {selector}: {exc}")
        
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        """Extract current page structure and interactive DNA."""
        self._ensure_browser()
        return {
            "url": self._page.url,
            "title": self._page.title(),
            "metadata": self._extract_metadata(),
            "components": self._discover_components(),
            "links": self._extract_links(),
        }

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
        """Perform deep discovery of all interactive components."""
        script = """() => {
            const gp = (e, p=[]) => { while(e.parentElement) { p.unshift(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')); e=e.parentElement; } return p.join(' > '); };
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
