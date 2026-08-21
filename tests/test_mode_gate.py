"""Regression tests for the mode-gate route handler (issue #60): in
`immutable` mode, every POST/PUT/PATCH/DELETE request must be fulfilled
with the synthetic response from `Prototype the synthetic fulfill()
response` (issue #57) *before* it reaches the network; in `stateful` mode
(the default), every request must reach the network unchanged.

Asserts at the network layer (did the request actually hit the server),
not the DOM layer - issue #57 already proved the synthetic response reads
as an ordinary success to the page's own JS; this ticket's own question is
narrower: did the real request get sent at all.
"""
import asyncio
import http.server
import json
import threading
from pathlib import Path
from typing import List, Tuple

import pytest

from spiders.browser.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"
_MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")


@pytest.fixture
def mutation_tracking_fixture_server():
    """Serves `tests/fixtures/mechanical/`, recording every (method, path)
    it actually receives for `/api/*` - the real target a mode-gate-blocked
    request must never reach. Answers with a real success body so
    `stateful` mode's control case (the request really lands) resolves the
    same way `immutable` mode's synthetic response is designed to mimic,
    rather than failing differently and confusing which mode caused what.
    """
    requests_seen: List[Tuple[str, str]] = []

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def _record_and_answer(self, method: str) -> None:
            requests_seen.append((method, self.path))
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            body = json.dumps({"id": 1, "name": "real"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self._record_and_answer("POST")

        def do_PUT(self):
            self._record_and_answer("PUT")

        def do_PATCH(self):
            self._record_and_answer("PATCH")

        def do_DELETE(self):
            self._record_and_answer("DELETE")

        def do_GET(self):
            requests_seen.append(("GET", self.path))
            super().do_GET()

        def log_message(self, format, *args):
            pass  # quiet - every request is already tracked in requests_seen

    handler = lambda *args, **kwargs: _Handler(*args, directory=str(FIXTURE_DIR), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", requests_seen
    server.shutdown()
    thread.join()


async def _create_and_delete(base_url: str, mode: str) -> tuple:
    url = f"{base_url}/mutation_response_handling.html"
    async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, mode=mode)) as crawler:
        await crawler.discover_page(url, session_id="s")
        create_state = await crawler.click(url, "s", "#createForm button[type=submit]")
        delete_state = await crawler.click(url, "s", "#deleteButton")
    return create_state, delete_state


def test_stateful_mode_lets_mutating_requests_reach_the_network(mutation_tracking_fixture_server):
    base_url, requests_seen = mutation_tracking_fixture_server

    asyncio.run(_create_and_delete(base_url, mode="stateful"))

    mutations = [r for r in requests_seen if r[0] in _MUTATING_METHODS]
    assert ("POST", "/api/items") in mutations
    assert ("DELETE", "/api/items/42") in mutations


def test_immutable_mode_blocks_mutating_requests_before_the_network(mutation_tracking_fixture_server):
    base_url, requests_seen = mutation_tracking_fixture_server

    asyncio.run(_create_and_delete(base_url, mode="immutable"))

    mutations = [r for r in requests_seen if r[0] in _MUTATING_METHODS]
    assert mutations == []


def test_immutable_mode_still_serves_ordinary_get_requests(mutation_tracking_fixture_server):
    """The mode-gate must be a scoped block, not a blanket page.route abort -
    the crawl still has to navigate and discover the rest of the site."""
    base_url, requests_seen = mutation_tracking_fixture_server

    asyncio.run(_create_and_delete(base_url, mode="immutable"))

    assert any(method == "GET" and path.endswith("mutation_response_handling.html")
               for method, path in requests_seen)


def test_immutable_mode_reports_each_block_on_its_own_click_result(mutation_tracking_fixture_server):
    """`PageState.blocked_mutations` (issue #62's link into the graph-store
    write path) has to name the interaction that caused it, not just that
    a block happened somewhere this crawl - the create click's block must
    read POST, the delete click's DELETE, never pooled together."""
    base_url, _requests_seen = mutation_tracking_fixture_server

    create_state, delete_state = asyncio.run(_create_and_delete(base_url, mode="immutable"))

    assert [m["method"] for m in create_state.blocked_mutations] == ["POST"]
    assert [m["method"] for m in delete_state.blocked_mutations] == ["DELETE"]


def test_stateful_mode_reports_no_blocked_mutations(mutation_tracking_fixture_server):
    base_url, _requests_seen = mutation_tracking_fixture_server

    create_state, delete_state = asyncio.run(_create_and_delete(base_url, mode="stateful"))

    assert create_state.blocked_mutations == []
    assert delete_state.blocked_mutations == []


def test_immutable_mode_blocks_mutating_get_requests(mutation_tracking_fixture_server):
    base_url, requests_seen = mutation_tracking_fixture_server

    async def _fetch_mutating_get(mode: str) -> None:
        url = f"{base_url}/mutation_response_handling.html"
        async with Crawl4AICrawler(Crawl4AICrawlerConfig(wait_seconds=0, mode=mode)) as crawler:
            await crawler.discover_page(url, session_id="s")
            await crawler.discover_page(f"{base_url}/api/items/42/delete", session_id="s")

    asyncio.run(_fetch_mutating_get("immutable"))

    get_mutations = [path for method, path in requests_seen if method == "GET" and "delete" in path]
    assert get_mutations == []

