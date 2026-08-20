"""Unit tests for generators/aria_tree.py - pure post-processing, so most
of this needs no live page: a captured aria_snapshot_yaml/axtree_json
pair is a fixture, the same way tests/test_document_pipeline.py fixtures
a graph store."""
import json

from core.documents import DocumentRequest
from generators.aria_tree import (
    _attach_axtree_refs,
    _axtree_preorder_node_indices,
    _parse_label,
    _structural_shape,
    _template_hash,
    _walk_aria_yaml,
    build_aria_tree,
)

SITE = "aria-tree-test-site"

# One screen's captured pair, hand-built to the shape spiders/content/
# accessibility_snapshot.py's real capture would produce: aria_snapshot_yaml
# a Playwright-style ariaSnapshot() string, axtree_json a CDP
# Accessibility.getFullAXTree response - deliberately out of array order,
# to prove the AXTree walk follows childIds, not array position.
_ARIA_YAML = '- heading "Welcome" [level=1]\n- list:\n    - listitem "Item 1"\n    - listitem "Item 2"\n'
_AXTREE_JSON = json.dumps({
    "nodes": [
        {"nodeId": "list1", "childIds": ["li1", "li2"]},
        {"nodeId": "root", "childIds": ["h1", "list1"]},
        {"nodeId": "li2", "childIds": []},
        {"nodeId": "h1", "childIds": []},
        {"nodeId": "li1", "childIds": []},
    ]
})


class StubAgent:
    def generate(self, prompt, system_instruction=None):
        return "STUB"


class StubStore:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def get_accessibility_snapshots(self):
        return self._snapshots


def _request(snapshots, run_id="20260820T000000Z"):
    store = StubStore(snapshots)
    return DocumentRequest(graph_store=store, site=SITE, agent=StubAgent(), settings={"run_id": run_id})


def test_parse_label_splits_role_and_quoted_name():
    assert _parse_label('heading "Welcome" [level=1]') == ("heading", "Welcome")
    assert _parse_label("generic") == ("generic", "")


def test_walk_aria_yaml_builds_nested_role_name_children():
    import yaml

    parsed = yaml.safe_load(_ARIA_YAML)
    nodes = _walk_aria_yaml(parsed)

    assert nodes[0] == {"role": "heading", "name": "Welcome", "children": []}
    assert nodes[1]["role"] == "list"
    assert [child["name"] for child in nodes[1]["children"]] == ["Item 1", "Item 2"]


def test_template_hash_ignores_name_but_not_role_or_hierarchy():
    """Two screens with the same roles/shape and different text collapse to
    one template; a screen with a different shape does not."""
    same_shape = [
        {"role": "heading", "name": "Different text entirely", "children": []},
        {"role": "list", "name": "", "children": [
            {"role": "listitem", "name": "x", "children": []},
            {"role": "listitem", "name": "y", "children": []},
        ]},
    ]
    original = _walk_aria_yaml_from_text(_ARIA_YAML)
    different_shape = [{"role": "heading", "name": "Welcome", "children": []}]

    assert _template_hash(original) == _template_hash(same_shape)
    assert _template_hash(original) != _template_hash(different_shape)


def _walk_aria_yaml_from_text(text):
    import yaml

    return _walk_aria_yaml(yaml.safe_load(text))


def test_axtree_preorder_follows_child_ids_not_array_order():
    axtree_nodes = json.loads(_AXTREE_JSON)["nodes"]

    order = _axtree_preorder_node_indices(axtree_nodes)

    # h1(3), list1(0), li1(4), li2(2) - the root's own entry (index 1) is
    # skipped, matching aria_snapshot("body")'s own children-only scope.
    assert order == [3, 0, 4, 2]


def test_attach_axtree_refs_pairs_nodes_in_matching_preorder():
    nodes = _walk_aria_yaml_from_text(_ARIA_YAML)
    axtree_nodes = json.loads(_AXTREE_JSON)["nodes"]

    _attach_axtree_refs(nodes, iter(_axtree_preorder_node_indices(axtree_nodes)))

    assert nodes[0]["x-axtree-ref"] == "/nodes/3"
    assert nodes[1]["x-axtree-ref"] == "/nodes/0"
    assert nodes[1]["children"][0]["x-axtree-ref"] == "/nodes/4"
    assert nodes[1]["children"][1]["x-axtree-ref"] == "/nodes/2"


def test_attach_axtree_refs_degrades_gracefully_on_a_shape_mismatch():
    """Fewer AXTree nodes than ARIA leaves: the unmatched tail carries no
    ref rather than a wrong one - docs/adr/0003's reserved-not-invented
    discipline, applied to a correlation failure instead of a missing field."""
    nodes = _walk_aria_yaml_from_text('- heading "A"\n- button "B"\n')

    _attach_axtree_refs(nodes, iter([7]))

    assert nodes[0]["x-axtree-ref"] == "/nodes/7"
    assert "x-axtree-ref" not in nodes[1]


def test_screen_id_is_deterministic_across_two_runs_of_the_same_site():
    snapshots = {"example.com/": {"aria_snapshot_yaml": _ARIA_YAML, "axtree_json": _AXTREE_JSON}}

    aria_first, _ = build_aria_tree(_request(snapshots))
    aria_second, _ = build_aria_tree(_request(snapshots))

    assert aria_first[0]["screen_id"] == aria_second[0]["screen_id"]
    assert aria_first[0]["screen_id"].startswith("SCR-")


def test_axtree_document_carries_run_id_and_matching_screen_ids():
    snapshots = {"example.com/": {"aria_snapshot_yaml": _ARIA_YAML, "axtree_json": _AXTREE_JSON}}

    aria_screens, axtree_document = build_aria_tree(_request(snapshots, run_id="R1"))

    assert axtree_document["run_id"] == "R1"
    assert axtree_document["screens"][0]["screen_id"] == aria_screens[0]["screen_id"]


def test_pages_with_no_captured_snapshot_contribute_no_screen():
    aria_screens, axtree_document = build_aria_tree(_request({}))

    assert aria_screens == []
    assert axtree_document["screens"] == []


def test_generated_document_validates_against_both_schemas():
    from core import bootstrap  # noqa: F401  (registers the document generators)
    from core.registry import DOCUMENT_REGISTRY

    snapshots = {"example.com/": {"aria_snapshot_yaml": _ARIA_YAML, "axtree_json": _AXTREE_JSON}}
    generator = DOCUMENT_REGISTRY.create("tree")

    outputs = generator.outputs(_request(snapshots))

    assert len(outputs) == 2
    by_filename = {output.filename: output for output in outputs}
    assert by_filename["tree.aria"].kind == "source" and by_filename["tree.aria"].extension == "yaml"
    assert by_filename["tree.axtree"].kind == "source" and by_filename["tree.axtree"].extension == "json"
