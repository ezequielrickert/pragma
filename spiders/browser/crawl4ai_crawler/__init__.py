"""Public surface of the crawl4ai_crawler package - re-exported so every
existing `from spiders.browser.crawl4ai_crawler import Crawl4AICrawler`
elsewhere in the codebase keeps working unchanged.
"""
from .config import Crawl4AICrawlerConfig
from .crawler import Crawl4AICrawler
from .session_aware_dispatcher import SessionAwareDispatcher

__all__ = ["Crawl4AICrawler", "Crawl4AICrawlerConfig", "SessionAwareDispatcher"]
