"""`tree.aria.yaml` + `tree.axtree.json`, per docs/adr/0003 - replaces the
hand-written component tree entirely, not just its serialization. Every
screen's real Playwright `ariaSnapshot()` (role + accessible name, the
same computation a screen reader does) is captured once per page during
the crawl (`spiders/content/accessibility_snapshot.py`,
`database/ladybug/accessibility_snapshot.py`); this module is pure
post-processing over what was captured - parsing, `SCR-<hash>`/
`template_hash` computation, and `x-axtree-ref` correlation, none of
which need a live page.

Details: docs/dev/generators/aria_tree.md#module
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Tuple

import yaml

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash

_ARIA_SCHEMA_PATH = "schemas/tree.aria.schema.json"
_AXTREE_SCHEMA_PATH = "schemas/tree.axtree.schema.json"

# Playwright's ariaSnapshot() label shape: `role "name" [attr=val ...]` or
# just `role` when there is no accessible name. The bracket attributes
# (level, checked, ...) are dropped here - ADR-0003 asks this document for
# role, name, and hierarchy, not the full attribute set.
_NAME_PATTERN = re.compile(r'"([^"]*)"')

Node = Dict[str, Any]


def _parse_label(label: str) -> Tuple[str, str]:
    """One ariaSnapshot() line's `(role, name)`.
    Details: docs/dev/generators/aria_tree.md#_parse_label
    """
    match = _NAME_PATTERN.search(label)
    if match:
        return label[: match.start()].strip(), match.group(1)
    return label.split("[")[0].strip(), ""


def _walk_aria_yaml(items: Any) -> List[Node]:
    """Playwright's ariaSnapshot() YAML, parsed, into `{role, name,
    children}` nodes - a leaf is a bare string; a node with children comes
    back from PyYAML as a single-key `{label: [children]}` mapping.
    Details: docs/dev/generators/aria_tree.md#_walk_aria_yaml
    """
    nodes = []
    for item in items or []:
        if isinstance(item, dict):
            (label, children), = item.items()
            role, name = _parse_label(label)
            nodes.append({"role": role, "name": name, "children": _walk_aria_yaml(children)})
        else:
            role, name = _parse_label(str(item))
            nodes.append({"role": role, "name": name, "children": []})
    return nodes


def _structural_shape(nodes: List[Node]) -> List[Any]:
    """Role and hierarchy only, name stripped - the input `template_hash`
    hashes (ADR-0003's duplicate/template detection).
    Details: docs/dev/generators/aria_tree.md#_structural_shape
    """
    return [[node["role"], _structural_shape(node["children"])] for node in nodes]


def _template_hash(nodes: List[Node]) -> str:
    shape = json.dumps(_structural_shape(nodes), separators=(",", ":"))
    return f"t-{short_hash(shape)}"


def _axtree_preorder_node_indices(axtree_nodes: List[Dict[str, Any]]) -> List[int]:
    """This screen's AXTree, walked via `childIds` (not array order, which
    CDP does not contractually guarantee), starting one level *below* each
    root - `getFullAXTree` includes the page's own RootWebArea entry, but
    `page.locator("body").aria_snapshot()` enumerates body's children, not
    body itself, so the walk skips exactly that one wrapper to keep both
    traversals describing the same starting set of nodes.
    Details: docs/dev/generators/aria_tree.md#_axtree_preorder_node_indices
    """
    index_by_id = {node["nodeId"]: position for position, node in enumerate(axtree_nodes)}
    referenced = {child_id for node in axtree_nodes for child_id in node.get("childIds", [])}
    roots = [node["nodeId"] for node in axtree_nodes if node["nodeId"] not in referenced]

    order: List[int] = []

    def visit(node_id: str) -> None:
        position = index_by_id.get(node_id)
        if position is None:
            return
        order.append(position)
        for child_id in axtree_nodes[position].get("childIds", []):
            visit(child_id)

    for root_id in roots:
        root_position = index_by_id.get(root_id)
        for child_id in axtree_nodes[root_position].get("childIds", []) if root_position is not None else ():
            visit(child_id)
    return order


def _attach_axtree_refs(nodes: List[Node], indices: Iterator[int]) -> None:
    """Tag every node with its `x-axtree-ref` by walking `nodes` in the same
    pre-order the AXTree indices were produced in, one index per node -
    never by matching role/name, which a page with duplicate siblings
    (two identical buttons) would attribute to the wrong one. A node left
    unmatched (the two trees disagreed on shape) simply carries no ref,
    per ADR-0003's own "reserved rather than invented" discipline.
    Details: docs/dev/generators/aria_tree.md#_attach_axtree_refs
    """
    for node in nodes:
        index = next(indices, None)
        if index is not None:
            node["x-axtree-ref"] = f"/nodes/{index}"
        _attach_axtree_refs(node["children"], indices)


def _aria_nodes(snapshot: Dict[str, Any]) -> List[Node]:
    return _walk_aria_yaml(yaml.safe_load(snapshot["aria_snapshot_yaml"]) or [])


def _build_screen(page_url: str, snapshot: Dict[str, Any]) -> Tuple[Node, ...]:
    """One page's captured snapshot into its `tree.aria.yaml` entry and its
    `tree.axtree.json` entry - a pair, since every `x-axtree-ref` in the
    first points into the second.
    Details: docs/dev/generators/aria_tree.md#_build_screen
    """
    screen_id = f"SCR-{short_hash(page_url)}"
    aria_nodes = _aria_nodes(snapshot)
    axtree_nodes = json.loads(snapshot["axtree_json"] or "{}").get("nodes", [])

    _attach_axtree_refs(aria_nodes, iter(_axtree_preorder_node_indices(axtree_nodes)))

    aria_entry = {
        "screen_id": screen_id, "route": page_url,
        # No state detection yet (ADR-0003's snapshot policy) - always
        # "default", reserved so a finding can already cite it.
        "state": "default",
        "template_hash": _template_hash(aria_nodes),
        "nodes": aria_nodes,
    }
    axtree_entry = {"screen_id": screen_id, "route": page_url, "nodes": axtree_nodes}
    return aria_entry, axtree_entry


def build_aria_tree(request: DocumentRequest) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """`(tree.aria.yaml's list, tree.axtree.json's dict)` for every page
    with a captured snapshot, in url order - a page discovered before this
    instrumentation existed, or whose capture failed, contributes neither.
    Details: docs/dev/generators/aria_tree.md#build_aria_tree
    """
    snapshots = request.graph_store.get_accessibility_snapshots()
    aria_screens = []
    axtree_screens = []
    for page_url in sorted(snapshots):
        aria_entry, axtree_entry = _build_screen(page_url, snapshots[page_url])
        aria_screens.append(aria_entry)
        axtree_screens.append(axtree_entry)
    axtree_document = {"run_id": request.settings.get("run_id", ""), "screens": axtree_screens}
    return aria_screens, axtree_document


def template_hash_by_page(request: DocumentRequest) -> Dict[str, str]:
    """`{page_url: template_hash}` for every page with a captured snapshot
    - the grouping `performance-baseline.json` needs (ADR-0026 point 2),
    without the full `tree.aria.yaml`/`tree.axtree.json` payload
    `build_aria_tree` produces. Same `_template_hash` computation,
    exposed once a second caller needed it.
    Details: docs/dev/generators/aria_tree.md#template_hash_by_page
    """
    snapshots = request.graph_store.get_accessibility_snapshots()
    return {page_url: _template_hash(_aria_nodes(snapshots[page_url])) for page_url in snapshots}


@DOCUMENT_REGISTRY.register("tree")
class AriaTreeDocument(DocumentGenerator):
    """Pipeline adapter for `build_aria_tree`.
    Details: docs/dev/generators/aria_tree.md#ariatreedocument
    """

    name = "tree"
    title = "ARIA Tree"
    purpose = "Every screen's accessibility tree - role, accessible name, and hierarchy, the way a screen reader sees it."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        aria_screens, axtree_document = build_aria_tree(request)
        validate_against_schema(aria_screens, _ARIA_SCHEMA_PATH)
        validate_against_schema(axtree_document, _AXTREE_SCHEMA_PATH)
        aria_content = yaml.safe_dump(aria_screens, sort_keys=False, allow_unicode=True)
        axtree_content = json.dumps(axtree_document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        return (
            DocumentOutput(filename="tree.aria", kind="source", extension="yaml", content=aria_content),
            DocumentOutput(filename="tree.axtree", kind="source", extension="json", content=axtree_content),
        )
