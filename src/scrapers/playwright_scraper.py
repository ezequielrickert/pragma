"""
Playwright-based stateful scraper for Pragma with high-fidelity discovery.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, ElementHandle

from ..interfaces import Scraper


class PlaywrightScraper(Scraper):
    """A high-fidelity scraper that maintains a browser session and discovers interactive depth."""

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
        # Give dynamic content a moment to settle
        time.sleep(1)
        return self.get_state()

    def click(self, selector: str) -> Dict[str, Any]:
        """Click an element, wait for state changes, and capture new deep state."""
        self._ensure_browser()
        try:
            # Handle text= selectors or raw CSS
            self._page.click(selector, timeout=5000)
            # Wait for either navigation or network to settle
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as exc:
            print(f"Warning: Interaction failed on {selector}: {exc}")
        
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        """Extract current page structure, interactive DNA, and relationships."""
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
        return self._page.evaluate("""() => {
            const meta = {};
            document.querySelectorAll('meta').forEach(m => {
                const name = m.getAttribute('name') || m.getAttribute('property');
                if (name) meta[name] = m.getAttribute('content');
            });
            return meta;
        }""")

    def _discover_components(self) -> List[Dict[str, Any]]:
        """Perform deep discovery of interactive components and their functional DNA."""
        # This script runs in the browser to find interactive elements and their context
        return self._page.evaluate("""() => {
            const getPath = (el) => {
                const path = [];
                while (el.parentElement) {
                    path.unshift(el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''));
                    el = el.parentElement;
                }
                return path.join(' > ');
            };

            const interactive = [];
            const selectors = 'button, a, input, select, textarea, [role="button"], [role="menuitem"], summary, .btn, .button';
            
            document.querySelectorAll(selectors).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    interactive.push({
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText.trim() || el.getAttribute('aria-label') || el.placeholder || '',
                        role: el.getAttribute('role') || '',
                        type: el.getAttribute('type') || '',
                        path: getPath(el),
                        attributes: {
                            id: el.id,
                            class: el.className,
                            href: el.getAttribute('href') || ''
                        },
                        isVisible: true
                    });
                }
            });
            return interactive;
        }""")

    def _extract_links(self) -> List[str]:
        """Gather all unique, relevant hrefs."""
        links = self._page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a'))
                .map(a => a.href)
                .filter(href => href.startsWith('http'));
        }""")
        return list(set(links))

    def close(self) -> None:
        """Shutdown browser and playwright."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
