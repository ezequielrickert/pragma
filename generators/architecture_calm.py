"""`architecture.calm.json`, `architecture.cyclonedx.json`, and
`architecture.md`, per docs/adr/0007 and docs/adr/0010.

`architecture.calm.json` (FINOS CALM 1.2) is reshaped from the same
`@graph` `generators/graph_export.py::build_export_graph` assembles - the
same call `export.json` itself made, not a second, independently-detected
structure (ADR-0010 point 4). CALM node ids reuse `export.json`'s own
node ids directly, so a CALM node is traceable back to its `export.json`
counterpart by id alone.

Betweenness/depth/bottleneck metrics are recomputed here via
`core/graph_metrics.py` rather than threaded through from
`build_export_graph` - `export.json`'s own schema (ADR-0002) has no room
for them, and nothing else needs them, so the small duplicate computation
keeps `export.json`'s consumer surface clean rather than growing it for
one downstream document.

Details: docs/dev/generators/architecture_calm.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.graph_metrics import NodeMetrics, compute_graph_metrics
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from utils.urls import route_shape
from .architecture_cyclonedx import build_cyclonedx_document
from .graph_export import build_export_graph

_CALM_SCHEMA_PATH = "schemas/architecture.calm.schema.json"
_CYCLONEDX_SCHEMA_PATH = "schemas/architecture.cyclonedx.schema.json"

# ADR-0010 point 6: pragma's own vocabulary as the literal node-type
# string, not force-fit into CALM's infra-shaped sanctioned kinds.
_NODE_TYPE_TO_CALM = {"Pantalla": "screen", "Componente": "component", "Endpoint": "endpoint", "Modulo": "module"}
_CONTAINMENT_PREDICATE = "contiene"
_CONNECTION_PREDICATES = ("navega_a", "dispara", "consume")

# ADR-0007 point 3's own wording: the 90th percentile.
_BOTTLENECK_PERCENTILE_LABEL = "90th"


def _calm_node(node: Dict[str, Any], metrics_by_id: Dict[str, NodeMetrics]) -> Dict[str, Any]:
    """One CALM node, plus pragma's `metadata.pragma` extension (ADR-0010
    point 7) when `core/graph_metrics.py` has facts about it.
    Details: docs/dev/generators/architecture_calm.md#_calm_node
    """
    calm_node: Dict[str, Any] = {
        "unique-id": node["id"],
        "node-type": _NODE_TYPE_TO_CALM.get(node["type"], node["type"].lower()),
        "name": node.get("label", node["id"]),
    }
    metric = metrics_by_id.get(node["id"])
    if metric is not None:
        calm_node["metadata"] = {
            "pragma": {
                "depth": metric.depth,
                "betweenness": round(metric.betweenness, 6),
                "is_bottleneck": metric.is_bottleneck,
            }
        }
    return calm_node


def _relationship_id(kind: str, *parts: str) -> str:
    return f"REL-{kind}-{short_hash('|'.join(parts))}"


def _composed_of_relationships(graph_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "unique-id": _relationship_id("composed-of", node["id"]),
            "relationship-type": {
                "composed-of": {"container": node["id"], "nodes": list(node[_CONTAINMENT_PREDICATE])}
            },
        }
        for node in graph_nodes
        if node.get(_CONTAINMENT_PREDICATE)
    ]


def _connects_relationships(graph_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relationships = []
    for node in graph_nodes:
        for predicate in _CONNECTION_PREDICATES:
            for target in node.get(predicate) or []:
                relationships.append(
                    {
                        "unique-id": _relationship_id(predicate, node["id"], target),
                        "relationship-type": {
                            "connects": {"source": {"node": node["id"]}, "destination": {"node": target}}
                        },
                    }
                )
    return relationships


def build_calm_document(request: DocumentRequest) -> Dict[str, Any]:
    """The full `architecture.calm.json` payload.
    Details: docs/dev/generators/architecture_calm.md#build_calm_document
    """
    export_document = build_export_graph(request)
    graph_nodes = export_document["@graph"]
    root = route_shape(request.settings.get("target", "")) or None
    metrics = compute_graph_metrics(graph_nodes, root=root)
    metrics_by_id = {metric.node_id: metric for metric in metrics.node_metrics}

    return {
        "$schema": "https://calm.finos.org/release/1.2/meta/calm.json",
        "nodes": [_calm_node(node, metrics_by_id) for node in graph_nodes],
        "relationships": _composed_of_relationships(graph_nodes) + _connects_relationships(graph_nodes),
    }


def _pragma_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    return node.get("metadata", {}).get("pragma", {})


def _modules_from_calm(calm_document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per `module` node: label, member count, depth range across
    its member screens - `architecture.md`'s Building Blocks section,
    never hand-authored in parallel with `architecture.calm.json`.
    Details: docs/dev/generators/architecture_calm.md#_modules_from_calm
    """
    nodes_by_id = {node["unique-id"]: node for node in calm_document["nodes"]}
    composed_of = {
        relationship["relationship-type"]["composed-of"]["container"]: relationship["relationship-type"]["composed-of"]["nodes"]
        for relationship in calm_document["relationships"]
        if "composed-of" in relationship["relationship-type"]
    }
    rows = []
    for node in calm_document["nodes"]:
        if node["node-type"] != "module":
            continue
        member_ids = composed_of.get(node["unique-id"], [])
        depths = [
            _pragma_metadata(nodes_by_id[member])["depth"]
            for member in member_ids
            if member in nodes_by_id and _pragma_metadata(nodes_by_id[member]).get("depth") is not None
        ]
        rows.append(
            {
                "label": node["name"], "member_count": len(member_ids),
                "shallowest": min(depths) if depths else None, "deepest": max(depths) if depths else None,
            }
        )
    return sorted(rows, key=lambda row: (-row["member_count"], row["label"]))


def _bottlenecks_from_calm(calm_document: Dict[str, Any]) -> List[Tuple[str, str]]:
    return sorted(
        (node["node-type"], node["unique-id"])
        for node in calm_document["nodes"]
        if _pragma_metadata(node).get("is_bottleneck")
    )


def _depth_label(shallowest: Optional[int], deepest: Optional[int]) -> str:
    if shallowest is None:
        return "unreachable from the entry point"
    return str(shallowest) if shallowest == deepest else f"{shallowest}-{deepest}"


def _context_section(calm_document: Dict[str, Any]) -> List[str]:
    counts: Dict[str, int] = {}
    for node in calm_document["nodes"]:
        counts[node["node-type"]] = counts.get(node["node-type"], 0) + 1
    return [
        "## Context", "",
        f"{counts.get('screen', 0)} screen(s), {counts.get('component', 0)} component(s), "
        f"{counts.get('endpoint', 0)} endpoint(s), grouped into {counts.get('module', 0)} module(s) - "
        "derived from the live crawl graph (docs/adr/0007), not hand-drawn.",
        "",
    ]


def _building_blocks_section(calm_document: Dict[str, Any]) -> List[str]:
    modules = _modules_from_calm(calm_document)
    lines = ["## Building blocks", ""]
    if not modules:
        return lines + ["No modules were detected - too few screens to cluster.", ""]
    lines += ["| Module | Screens | Depth |", "|---|---|---|"]
    lines += [
        f"| {m['label']} | {m['member_count']} | {_depth_label(m['shallowest'], m['deepest'])} |" for m in modules
    ]
    return lines + [""]


def _deployment_view_section(cyclonedx_document: Dict[str, Any]) -> List[str]:
    services = cyclonedx_document.get("externalServices", [])
    lines = ["## Deployment view", "", "Third-party services this application depends on.", ""]
    if not services:
        return lines + ["No third-party HTTP traffic was observed.", ""]
    lines += ["| Service | Calls observed |", "|---|---|"]
    for service in services:
        calls = next(
            (p["value"] for p in service["properties"] if p["name"] == "pragma:evidence:observationCount"), "0"
        )
        lines.append(f"| {service['name']} | {calls} |")
    return lines + [""]


def _risks_section(calm_document: Dict[str, Any]) -> List[str]:
    bottlenecks = _bottlenecks_from_calm(calm_document)
    lines = ["## Risks", ""]
    if not bottlenecks:
        return lines + ["No node stood out as a single point of passage in this crawl.", ""]
    lines += [
        f"{len(bottlenecks)} single point(s) of passage ({_BOTTLENECK_PERCENTILE_LABEL}-percentile "
        "betweenness, in-degree 3+): removing one narrows or disconnects the paths through it.",
        "",
        "| Type | Node |", "|---|---|",
    ]
    lines += [f"| {node_type} | {node_id} |" for node_type, node_id in bottlenecks]
    return lines + [""]


def _render_architecture_view(calm_document: Dict[str, Any], cyclonedx_document: Dict[str, Any], site: str) -> str:
    """`architecture.md`, arc42-shaped (ADR-0010 point 3) - mechanically
    rendered from both source documents, never hand-authored in parallel.
    Details: docs/dev/generators/architecture_calm.md#_render_architecture_view
    """
    lines = [f"# Architecture: {site}", ""]
    lines += _context_section(calm_document)
    lines += _building_blocks_section(calm_document)
    lines += _deployment_view_section(cyclonedx_document)
    lines += _risks_section(calm_document)
    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("architecture")
class ArchitectureDocument(DocumentGenerator):
    """Three files: `architecture.calm.json` and `architecture.cyclonedx.json`
    (source, both schema-validated), `architecture.md` (view, arc42-shaped).
    Details: docs/dev/generators/architecture_calm.md#architecturedocument
    """

    name = "architecture"
    title = "Architecture"
    purpose = (
        "Module structure and dependency graph as FINOS CALM, third-party integrations as CycloneDX, "
        "and an arc42 view rendered from both."
    )

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        calm_document = build_calm_document(request)
        validate_against_schema(calm_document, _CALM_SCHEMA_PATH)

        cyclonedx_document = build_cyclonedx_document(request.graph_store.integrations())
        validate_against_schema(cyclonedx_document, _CYCLONEDX_SCHEMA_PATH)

        view = _render_architecture_view(calm_document, cyclonedx_document, request.site)
        return (
            DocumentOutput(filename="architecture.calm", kind="source", extension="json", content=_as_json(calm_document)),
            DocumentOutput(filename="architecture.cyclonedx", kind="source", extension="json", content=_as_json(cyclonedx_document)),
            DocumentOutput(filename="architecture", kind="view", extension="md", content=view),
        )
