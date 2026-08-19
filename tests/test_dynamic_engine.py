"""Regression tests for `pragma dynamic`'s own entry point
(core/dynamic_engine.py): proves the resume-vs-fallback decision and that
a real fixture crawl still works end to end when there is nothing to
resume.
"""
import asyncio
import http.server
import threading
from pathlib import Path

import pytest

from core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
from core.config import PragmaConfig
from core.data_contracts import ComponentFamily
from core.dynamic_engine import DynamicEngine
from core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY
from database.ladybug.store import LadybugGraphStore
from spiders.orchestration.graph_sink import GraphStoreSink
from utils.urls import route_shape

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


def test_dynamic_falls_back_to_independent_discovery_when_nothing_was_scouted(fixture_server):
    graph_store = GRAPH_STORE_REGISTRY.create("memory", site="fixture.example")
    graph_store.connect()
    engine = DynamicEngine(
        AGENT_REGISTRY.create("mock"), graph_store, max_pages=15, page_concurrency=2,
        login_enabled=False, ai_fill_values=False,
    )

    result = asyncio.run(engine.run(fixture_server + "/index.html"))

    assert result.resumed_from_static is False
    assert result.pages_finished > 0
    assert result.families_sampled == 0


def test_dynamic_engine_from_config_derives_site_from_the_url():
    config = PragmaConfig(url="http://dynamic-site.example/", graph_store="memory", login_enabled=False)
    engine = DynamicEngine.from_config(config)

    assert engine.site == "dynamic-site.example"


def test_dynamic_resumes_and_wires_a_family_sampler_when_static_and_cluster_already_ran(tmp_path, monkeypatch):
    site = "resumable.example"
    graph_store = LadybugGraphStore(site, directory=str(tmp_path))
    graph_store.connect()

    start_url = "http://resumable.example/"
    page_key = route_shape(start_url)
    sink = GraphStoreSink(graph_store, base_url=start_url)
    asyncio.run(sink.record_page_arrival(page_key, description="", title=""))
    asyncio.run(sink.record_page_scouted(page_key, 2))
    graph_store.record_component(page_key, "#a", tag="button", text="Add", component_type="submit button")
    graph_store.record_component(page_key, "#b", tag="button", text="Add", component_type="submit button")
    graph_store.record_component_families(
        [ComponentFamily(
            tag="button", component_type="submit button", common_classes=(),
            member_paths=((page_key, "#a"), (page_key, "#b")),
        )]
    )

    captured_configs = []

    class _FakeCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

    class _FakeMechanicalCrawler:
        def __init__(self, crawler, config=None):
            captured_configs.append(config)

        async def crawl_site(self, start_url):
            return []

    monkeypatch.setattr("core.dynamic_engine.Crawl4AICrawler", lambda config: _FakeCrawler())
    monkeypatch.setattr("core.dynamic_engine.MechanicalCrawler", _FakeMechanicalCrawler)

    engine = DynamicEngine(AGENT_REGISTRY.create("mock"), graph_store, site=site, login_enabled=False)
    result = asyncio.run(engine.run(start_url))

    assert result.resumed_from_static is True
    assert result.families_sampled == 1
    assert captured_configs[0].interact_only is True
    assert captured_configs[0].family_sampler is not None
