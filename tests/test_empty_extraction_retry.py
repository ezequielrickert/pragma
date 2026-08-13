"""The retry that fires when discovery comes back empty on a page that
clearly has content (src/crawlers/crawl4ai_crawler.py).

Driven through a real browser against fixtures, because the bug this
exists for is a timing race: a shell that settles, then swaps in the real
screen a second later. Nothing short of a real render reproduces it.
"""
import asyncio
import http.server
import threading
from pathlib import Path

import pytest

from src.crawlers.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "late_render"


@pytest.fixture(scope="module")
def fixture_server():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(FIXTURE_DIR), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()


def _discover(url, wait_seconds):
    async def run():
        config = Crawl4AICrawlerConfig(headless=True, wait_seconds=wait_seconds)
        async with Crawl4AICrawler(config) as crawler:
            return await crawler.discover_page(url)

    return asyncio.run(run())


def test_a_screen_that_renders_late_is_found_on_the_retry(fixture_server):
    """The real failure: `before_retrieve_html` logged 0 components against
    21,891 characters of HTML, and the crawl recorded one page and nothing
    else. The settle-wait returned on the shell; the screen came later."""
    state = _discover(f"{fixture_server}/slow.html", wait_seconds=0.6)

    # The anchor is both a discovered component and a link - discovery
    # matches `a` tags, and extract_links reads the same element.
    assert sorted(c["text"] for c in state.components) == ["Comprar", "Otra pagina"]
    assert len(state.links) == 1


def test_a_page_that_genuinely_has_nothing_is_not_retried_into_existence(fixture_server):
    """A legal notice really does have no controls and no links. The retry
    must leave it empty rather than keep looking."""
    state = _discover(f"{fixture_server}/static.html", wait_seconds=0.6)

    assert state.components == []
    assert state.links == []
    assert state.title == "Solo texto"


def test_a_redirecting_shell_is_retried_even_though_it_is_tiny(fixture_server):
    """The measurement that removed the node guard: empanad.app's landing
    holds at 35 nodes with no controls, redirects, and the destination sits
    at 36 nodes with no controls for another 0.4s before rendering. Both
    plateaus are below any "this page is substantial" threshold, so gating
    the retry on size skipped exactly the case it was written for."""
    state = _discover(f"{fixture_server}/tiny_shell.html", wait_seconds=0.6)

    assert [c["text"] for c in state.components] == ["Entrar"]
