"""End-to-end smoke test for Engine._run_async - the full crawl+synthesize
pipeline against a real fixture site, asserting both output documents (the
prose PRD and the new component-tree, Phase 5) get written with real content.
"""
import http.server
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from src.core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
from src.core.engine import Engine, EngineRunResult, _resolve_pool_size
from src.core.registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY
from src.crawlers.fill_value_agent import FILL_VALUE_SYSTEM_INSTRUCTION

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mechanical"


def test_resolve_pool_size_defaults_to_page_concurrency_when_unset():
    """browser_pool_size=None must mean one dedicated browser per worker -
    the pre-existing 1:1 behavior, unchanged for anyone who never sets it."""
    assert _resolve_pool_size(None, page_concurrency=8) == 8


def test_resolve_pool_size_honors_a_smaller_explicit_value():
    """A lower browser_pool_size decouples worker count from browser count -
    several workers sharing each browser process."""
    assert _resolve_pool_size(3, page_concurrency=8) == 3


def test_resolve_pool_size_clamps_a_value_above_page_concurrency():
    """A pool member no worker is ever routed to would launch and sit idle -
    browser_pool_size can't usefully exceed page_concurrency."""
    assert _resolve_pool_size(20, page_concurrency=8) == 8


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


def test_engine_run_produces_prd_and_tree_documents(fixture_server):
    out_dir = tempfile.mkdtemp()
    try:
        agent = AGENT_REGISTRY.create("mock")
        graph_store = GRAPH_STORE_REGISTRY.create("memory")
        graph_store.connect()
        engine = Engine(
            agent,
            graph_store,
            out_dir=out_dir,
            element_budget=200,
            max_pages=15,
            wait_seconds=0,
            debug_logs_dir="",  # no debug artifacts needed for this smoke test
        )
        result = engine.run(f"{fixture_server}/index.html")

        assert isinstance(result, EngineRunResult)
        assert os.path.exists(result.prd_path)
        assert os.path.exists(result.tree_path)

        tree_text = Path(result.tree_path).read_text(encoding="utf-8")
        assert "# Component Tree:" in tree_text
        assert "Mechanical loop fixture: index" in tree_text
        assert "A paragraph of real page text" in tree_text

        prd_text = Path(result.prd_path).read_text(encoding="utf-8")
        assert prd_text  # mock agent's own output, non-empty
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


class _TrackingAgent:
    """Records every system_instruction it's asked to generate under -
    used to prove ai_fill_values=False never invokes the per-field fill-value
    call (FILL_VALUE_SYSTEM_INSTRUCTION), without poisoning the *other*,
    legitimate agent.generate() call PRD synthesis makes after the crawl -
    a blanket "raise if called at all" double would break that unrelated
    call too."""

    def __init__(self) -> None:
        self.system_instructions_used = []

    def generate(self, prompt: str, system_instruction=None) -> str:
        self.system_instructions_used.append(system_instruction)
        return "mock output"


def test_ai_fill_values_false_skips_the_per_field_agent_call(fixture_server):
    """The speed knob this was built for: ai_fill_values=False must mean the
    per-fillable-field AI round trip never happens at all (falls back to the
    fast deterministic placeholder), not just "usually skipped"."""
    out_dir = tempfile.mkdtemp()
    try:
        agent = _TrackingAgent()
        graph_store = GRAPH_STORE_REGISTRY.create("memory")
        graph_store.connect()
        engine = Engine(
            agent,
            graph_store,
            out_dir=out_dir,
            element_budget=200,
            max_pages=15,
            wait_seconds=0,
            debug_logs_dir="",
            ai_fill_values=False,
        )
        engine.run(f"{fixture_server}/index.html")
        assert FILL_VALUE_SYSTEM_INSTRUCTION not in agent.system_instructions_used
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_engine_run_records_manifest_and_skips_export_by_default(fixture_server):
    """docs/explicativos/plan-almacenamiento.md Fase A: every run is recorded
    in docs/runs.json unconditionally, but the JSON graph export is opt-in -
    off by default must mean genuinely absent, not just unmentioned."""
    out_dir = tempfile.mkdtemp()
    try:
        agent = AGENT_REGISTRY.create("mock")
        graph_store = GRAPH_STORE_REGISTRY.create("memory")
        graph_store.connect()
        engine = Engine(
            agent, graph_store, out_dir=out_dir, element_budget=200, max_pages=15,
            wait_seconds=0, debug_logs_dir="",
        )
        result = engine.run(f"{fixture_server}/index.html")

        assert result.export_path is None
        assert not list(Path(out_dir).glob("*_graph_*.json"))

        assert result.manifest_path == str(Path(out_dir) / "runs.json")
        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        site = next(iter(manifest))
        entry = manifest[site][-1]
        assert entry["prd_path"] == result.prd_path
        assert entry["tree_path"] == result.tree_path
        assert entry["export_path"] is None
        assert entry["pages_total"] >= 1
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_engine_run_export_json_writes_a_third_document(fixture_server):
    out_dir = tempfile.mkdtemp()
    try:
        agent = AGENT_REGISTRY.create("mock")
        graph_store = GRAPH_STORE_REGISTRY.create("memory")
        graph_store.connect()
        engine = Engine(
            agent, graph_store, out_dir=out_dir, element_budget=200, max_pages=15,
            wait_seconds=0, debug_logs_dir="", export_json=True,
        )
        result = engine.run(f"{fixture_server}/index.html")

        assert result.export_path is not None
        assert os.path.exists(result.export_path)
        export_data = json.loads(Path(result.export_path).read_text(encoding="utf-8"))
        assert export_data["pages"]

        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        site = next(iter(manifest))
        assert manifest[site][-1]["export_path"] == result.export_path
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_engine_run_regenerates_docs_index(fixture_server):
    """docs/explicativos/plan-almacenamiento.md Fase E: docs/index.md must be
    (re)written every run, unconditionally, linking to this run's own PRD."""
    out_dir = tempfile.mkdtemp()
    try:
        agent = AGENT_REGISTRY.create("mock")
        graph_store = GRAPH_STORE_REGISTRY.create("memory")
        graph_store.connect()
        engine = Engine(
            agent, graph_store, out_dir=out_dir, element_budget=200, max_pages=15,
            wait_seconds=0, debug_logs_dir="",
        )
        result = engine.run(f"{fixture_server}/index.html")

        # index_path is built the same forward-slash-f-string way as
        # prd_path/tree_path/export_path elsewhere in Engine._run_async, not
        # via Path() joining (which would use the platform's native
        # separator) - match that convention here rather than Path().
        assert result.index_path == f"{out_dir}/index.md"
        assert os.path.exists(result.index_path)
        index_text = Path(result.index_path).read_text(encoding="utf-8")
        assert "# Pragma run index" in index_text
        assert Path(result.prd_path).name in index_text
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
