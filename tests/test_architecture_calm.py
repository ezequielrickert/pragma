"""Unit tests for generators/architecture_calm.py - built against a stub
graph store (the same shape tests/test_graph_export.py uses), since
build_calm_document reads through build_export_graph."""
import json

from core.documents import DocumentRequest
from generators.architecture_calm import (
    ArchitectureDocument,
    _bottlenecks_from_calm,
    _modules_from_calm,
    build_calm_document,
)

SITE = "architecture-test-site"


class StubAgent:
    def generate(self, prompt, system_instruction=None):
        return "STUB"


class StubStore:
    def __init__(self, pages, edges=()):
        self._pages = pages
        self._edges = edges

    def get_progress_table_rows(self):
        return [{"url": url, "status": "Finished"} for url in self._pages]

    def get_page_titles(self):
        return {}

    def get_page_descriptions(self):
        return {}

    def get_component_ledger(self):
        return {}

    def get_state_styles(self):
        return []

    def get_inferred_requests(self):
        return []

    def get_edges(self):
        return list(self._edges)

    def integrations(self):
        return [{"host": "cdn.example.com", "method": "GET", "path_pattern": "/x", "call_count": 5}]


def _request(store, target=""):
    return DocumentRequest(graph_store=store, site=SITE, agent=StubAgent(), settings={"run_id": "R1", "target": target})


def test_calm_document_carries_a_screen_node_per_page():
    store = StubStore(["example.com/", "example.com/admin/a", "example.com/admin/b"])

    document = build_calm_document(_request(store))

    screen_ids = {n["unique-id"] for n in document["nodes"] if n["node-type"] == "screen"}
    assert screen_ids == {"example.com/", "example.com/admin/a", "example.com/admin/b"}


def test_calm_document_carries_a_module_node_and_a_composed_of_relationship():
    store = StubStore(["example.com/admin/a", "example.com/admin/b"])

    document = build_calm_document(_request(store))

    module = next(n for n in document["nodes"] if n["node-type"] == "module")
    composed_of = next(
        r["relationship-type"]["composed-of"]
        for r in document["relationships"]
        if "composed-of" in r["relationship-type"] and r["relationship-type"]["composed-of"]["container"] == module["unique-id"]
    )
    assert set(composed_of["nodes"]) == {"example.com/admin/a", "example.com/admin/b"}


def test_navigation_edges_become_connects_relationships():
    store = StubStore(
        ["example.com/", "example.com/a"],
        edges=[{"from": "example.com/", "to": "example.com/a", "component": ""}],
    )

    document = build_calm_document(_request(store))

    connects = [r["relationship-type"]["connects"] for r in document["relationships"] if "connects" in r["relationship-type"]]
    assert any(c["source"]["node"] == "example.com/" and c["destination"]["node"] == "example.com/a" for c in connects)


def test_depth_metadata_is_populated_from_the_given_root():
    """The root page's own id is already what route_shape produces for
    it - the same canonical form every stored Page.url takes - so the
    target setting has to be route_shaped before it can match."""
    store = StubStore(
        ["example.com", "example.com/a"],
        edges=[{"from": "example.com", "to": "example.com/a", "component": ""}],
    )

    document = build_calm_document(_request(store, target="example.com/"))

    root_node = next(n for n in document["nodes"] if n["unique-id"] == "example.com")
    child_node = next(n for n in document["nodes"] if n["unique-id"] == "example.com/a")
    assert root_node["metadata"]["pragma"]["depth"] == 0
    assert child_node["metadata"]["pragma"]["depth"] == 1


def test_modules_from_calm_reports_member_count_and_depth_range():
    store = StubStore(["example.com/admin/a", "example.com/admin/b"])
    document = build_calm_document(_request(store))

    modules = _modules_from_calm(document)

    assert modules[0]["label"] == "Admin"
    assert modules[0]["member_count"] == 2


def test_bottlenecks_from_calm_reads_the_is_bottleneck_flag():
    hub_targets = [f"example.com/spoke{i}" for i in range(4)]
    store = StubStore(
        ["example.com/hub", *hub_targets],
        edges=(
            [{"from": "example.com/hub", "to": t, "component": ""} for t in hub_targets]
            + [{"from": t, "to": "example.com/hub", "component": ""} for t in hub_targets]
        ),
    )
    document = build_calm_document(_request(store))

    bottlenecks = _bottlenecks_from_calm(document)

    assert ("screen", "example.com/hub") in bottlenecks


def test_generate_returns_the_calm_cyclonedx_and_view_triple():
    store = StubStore(["example.com/"])

    outputs = ArchitectureDocument().outputs(_request(store))

    assert [o.filename for o in outputs] == ["architecture.calm", "architecture.cyclonedx", "architecture"]
    assert [(o.kind, o.extension) for o in outputs] == [
        ("source", "json"), ("source", "json"), ("view", "md"),
    ]
    json.loads(outputs[0].content)
    json.loads(outputs[1].content)


def test_the_view_reports_context_building_blocks_deployment_and_risks():
    store = StubStore(["example.com/admin/a", "example.com/admin/b"])

    view = ArchitectureDocument().outputs(_request(store))[2].content

    assert "## Context" in view
    assert "## Building blocks" in view
    assert "## Deployment view" in view
    assert "## Risks" in view
    assert "cdn.example.com" in view
