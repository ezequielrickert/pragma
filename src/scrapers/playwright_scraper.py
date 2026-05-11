from typing import Dict, Any
from ..interfaces import Scraper
from playwright.sync_api import sync_playwright

class PlaywrightScraper(Scraper):
    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape(self, url: str) -> Dict[str, Any]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(url, wait_until='load')
            html = page.content()
            links = [el.get_attribute('href') for el in page.query_selector_all('a') if el.get_attribute('href')]
            browser.close()
        return {'url': url, 'html': html, 'links': links}
