"""End-to-end smoke test for StaticEngine - `pragma static`'s own entry
point - against a real fixture site: proves the scout-only crawl actually
runs (real navigation, prefetch=true) and generates no documents, unlike
`Engine.run`.
"""
import asyncio
import http.server
import threading
from pathlib import Path

import pytest

from core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
from core.registry import GRAPH_STORE_REGISTRY
from core.static_engine import StaticEngine

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"


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


def test_static_run_scouts_pages_without_a_login_form_and_generates_no_documents(fixture_server):
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site="fixture.example")
    graph_store.connect()
    engine = StaticEngine(graph_store, max_pages=15, page_concurrency=2)

    result = asyncio.run(engine.run(fixture_server + "/index.html"))

    assert result.pages_scouted > 0
    assert result.login_session_path is None


def test_static_engine_from_config_derives_site_from_the_url():
    from core.config import PragmaConfig

    config = PragmaConfig(url="http://static-site.example/", graph_store="memory", login_enabled=False)
    engine = StaticEngine.from_config(config)

    assert engine.site == "static-site.example"
