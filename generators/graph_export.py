"""JSON-LD snapshot of the crawl's live graph, per docs/adr/0002.

Kùzu remains the query engine; this is a portable, git-diffable export
for downstream interop (`usability`'s EARL findings cite this vocabulary
by node id) - not a second queryable store. `Pantalla`/`Componente`/
`Endpoint`/`Token`/`Modulo`/`Entidad`/`Requisito` and the edges
`contiene`/`navega_a`/`dispara`/`consume`/`depende_de`/`implementa`/
`cubre` are populated from real graph-store queries today (`Token` since
ticket #100; `Modulo` since ticket #102 via `core/graph_metrics.py`'s
hybrid path-prefix/Leiden derivation, ADR-0007; `Entidad`/`depende_de`
since ticket #103, ADR-0008 point 5; `Requisito`/`implementa`/`cubre`
since ticket #104, ADR-0009 point 5 - ADR-0002 point 5's own "wire
population edges as those tickets land"); `Escenario`/`Hallazgo`/`Flujo`/
`Estado` and the `usa_token` edge stay reserved - present in
`schemas/export.schema.json`'s `type` enum and
`schemas/export.context.jsonld`, absent from `@graph` until their own
document's ticket starts emitting them (`usa_token` needs `catalog`'s
`x-tokens` links, ADR-0006 - split into
[ticket #126](https://github.com/ezequielrickert/pragma/issues/126);
`Requisito`'s own `depende_de` edge between requirements stays empty
too - `links.depends_on` is reserved in `requirements.json` itself,
`generators/requirements.py` has no dependency-detection rule yet).

`@context` is the schema-locked literal `"./export.context.jsonld"`
(`schemas/export.context.jsonld` in the repo) - the same non-fetchable-
identifier convention every schema's own `$id` already uses in this
codebase (`https://pragma.local/schemas/...`), not a promise that the
file sits next to every generated `export.json`.

Details: docs/dev/generators/graph_export.md#module
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.graph_metrics import compute_graph_metrics
from core.registry import DOCUMENT_REGISTRY
from database.ladybug.ids import component_id
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from utils.urls import route_shape
from .data_model import build_data_model_document
from .design_tokens import build_tokens_document
from .requirements import build_requirements_document

_SCHEMA_PATH = "schemas/export.schema.json"

# A page this crawl only ever discovered a link to, never counted as
# something it owed a visit (database/ladybug/page.py::count_visited
# excludes it the same way) - not a screen of the audited application,
# so it gets no Pantalla node. A navega_a edge toward one is dropped
# rather than left dangling into a node absent from @graph.
_EXTERNAL_STATUS = "External"

Node = Dict[str, Any]


def _pantalla_nodes(
    pages: List[Dict[str, Any]], titles: Dict[str, str], descriptions: Dict[str, str]
) -> Dict[str, Node]:
    """One `Pantalla` per crawled page, keyed by url - `External` pages
    excluded (see module docstring).
    Details: docs/dev/generators/graph_export.md#_pantalla_nodes
    """
    nodes = {}
    for row in pages:
        url = row["url"]
        if row.get("status") == _EXTERNAL_STATUS:
            continue
        nodes[url] = {"id": url, "type": "Pantalla", "label": titles.get(url) or descriptions.get(url) or url}
    return nodes


def _componente_nodes(component_ledger: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Node]:
    """One `Componente` per `(page, path)` the ledger already groups by.
    Details: docs/dev/generators/graph_export.md#_componente_nodes
    """
    nodes = {}
    for page_url, components in component_ledger.items():
        for path, record in components.items():
            node_id = component_id(page_url, path)
            nodes[node_id] = {"id": node_id, "type": "Componente", "label": record.get("text") or record.get("tag") or path}
    return nodes


def _endpoint_nodes(inferred_requests: Iterable[Any]) -> Dict[str, Node]:
    """One `Endpoint` per distinct first-party call, keyed the same way
    `database/ladybug/ids.py::endpoint_id` keys the graph's own `Endpoint`
    nodes - `InferredRequest.endpoint` is already `host` + the same
    path-pattern shape that function's `path_pattern` argument is.
    Details: docs/dev/generators/graph_export.md#_endpoint_nodes
    """
    nodes = {}
    for request in inferred_requests:
        node_id = f"{request.method} {request.endpoint}"
        nodes[node_id] = {"id": node_id, "type": "Endpoint", "label": node_id}
    return nodes


def _walk_token_groups(group: Dict[str, Any], path_prefix: str) -> Dict[str, Node]:
    """Recurse `tokens.json`'s `core`/`semantic` tree into `Token` nodes,
    keyed by dot-joined path (`core.color.text-1`) - a token's own
    position in the tree is already a short, stable, human-legible
    identity, unlike a `Page`/`Component`/`Endpoint`'s (a URL, a CSS
    selector, a host+path), which need `short_hash` because their
    natural identity is too long to use directly.
    Details: docs/dev/generators/graph_export.md#_walk_token_groups
    """
    nodes: Dict[str, Node] = {}
    for key, value in group.items():
        node_id = f"{path_prefix}.{key}"
        if "$value" in value:
            nodes[node_id] = {"id": node_id, "type": "Token", "label": node_id}
        else:
            nodes.update(_walk_token_groups(value, node_id))
    return nodes


def _token_nodes(tokens_document: Dict[str, Any]) -> Dict[str, Node]:
    """One `Token` per DTCG token in `tokens.json`'s `core`/`semantic`
    groups (docs/adr/0005 point 5) - built from the same
    `build_tokens_document` call `tokens.json` itself makes, not read back
    from that document's file, so the two always agree within one run.
    Details: docs/dev/generators/graph_export.md#_token_nodes
    """
    nodes: Dict[str, Node] = {}
    for group_name in ("core", "semantic"):
        nodes.update(_walk_token_groups(tokens_document.get(group_name, {}), group_name))
    return nodes


def _modulo_nodes(pantallas: Dict[str, Node], root: Optional[str]) -> Dict[str, Node]:
    """`Modulo` nodes, each `contiene`-ing its member `Pantalla` nodes -
    docs/adr/0007's hybrid path-prefix/Leiden derivation
    (`core/graph_metrics.py`), populating `export.json`'s reserved
    `Modulo` entities (ADR-0002) since ticket #102.
    Details: docs/dev/generators/graph_export.md#_modulo_nodes
    """
    metrics = compute_graph_metrics(list(pantallas.values()), root=root)
    modules: Dict[str, Node] = {}
    for assignment in metrics.node_modules:
        module = modules.setdefault(
            assignment.module_id,
            {"id": assignment.module_id, "type": "Modulo", "label": assignment.module_label or assignment.module_id},
        )
        _add_edge(module, "contiene", assignment.node_id)
    return modules


def _entidad_nodes(data_model_document: Dict[str, Any], endpoints: Dict[str, Node]) -> Dict[str, Node]:
    """One `Entidad` per `data-model.json` entity, with `depende_de` added
    onto the citing `Endpoint` node - ADR-0008 point 5's own edge
    direction, from the citing Endpoint to its Entidad, populating
    `export.json`'s reserved `Entidad` type since ticket #103. Built from
    the same `build_data_model_document` call `data-model.json` itself
    makes, not read back from its file.
    Details: docs/dev/generators/graph_export.md#_entidad_nodes
    """
    entidades: Dict[str, Node] = {}
    for entity_name, entity in data_model_document["entities"].items():
        entidades[entity_name] = {"id": entity_name, "type": "Entidad", "label": entity_name}
        for field in entity["fields"].values():
            for endpoint_id in field["observed_in"]["api_endpoints"]:
                endpoint = endpoints.get(endpoint_id)
                if endpoint is not None:
                    _add_edge(endpoint, "depende_de", entity_name)
    return entidades


def _requisito_nodes(
    requirements_document: Dict[str, Any], pantallas: Dict[str, Node],
    endpoints: Dict[str, Node], entidades: Dict[str, Node],
) -> Dict[str, Node]:
    """One `Requisito` per `requirements.json` entry, with `implementa`
    added onto the citing `Pantalla`/`Endpoint` node (from
    `links.screens`/`.endpoints`) and `cubre` added onto the `Requisito`
    itself (toward its `links.data_entities`) - ADR-0009 point 5.
    `links.depends_on` stays empty in `requirements.json` itself (no
    dependency-detection rule exists yet), so no `depende_de` edge
    between `Requisito` nodes populates either - reserved, not invented.
    Built from the same `build_requirements_document` call
    `requirements.json` itself makes, not read back from its file.
    Details: docs/dev/generators/graph_export.md#_requisito_nodes
    """
    pantallas_by_screen_id = {f"SCR-{short_hash(page_url)}": node for page_url, node in pantallas.items()}
    requisitos: Dict[str, Node] = {}
    for requirement in requirements_document["requirements"]:
        requirement_id = requirement["id"]
        requisitos[requirement_id] = {"id": requirement_id, "type": "Requisito", "label": requirement["syntax_text"]}
        for screen_id in requirement["links"]["screens"]:
            pantalla = pantallas_by_screen_id.get(screen_id)
            if pantalla is not None:
                _add_edge(pantalla, "implementa", requirement_id)
        for endpoint_id in requirement["links"]["endpoints"]:
            endpoint = endpoints.get(endpoint_id)
            if endpoint is not None:
                _add_edge(endpoint, "implementa", requirement_id)
        for entity_name in requirement["links"]["data_entities"]:
            if entity_name in entidades:
                _add_edge(requisitos[requirement_id], "cubre", entity_name)
    return requisitos


def _add_edge(node: Node, predicate: str, target_id: str) -> None:
    targets = node.setdefault(predicate, [])
    if target_id not in targets:
        targets.append(target_id)


def _populate_contiene(pantallas: Dict[str, Node], component_ledger: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    """Pantalla contiene Componente - one edge per pair the ledger groups by.
    Details: docs/dev/generators/graph_export.md#_populate_contiene
    """
    for page_url, components in component_ledger.items():
        pantalla = pantallas.get(page_url)
        if pantalla is None:
            continue
        for path in components:
            _add_edge(pantalla, "contiene", component_id(page_url, path))


def _populate_navega_a(pantallas: Dict[str, Node], componentes: Dict[str, Node], edges: List[Dict[str, Any]]) -> None:
    """Componente navega_a Pantalla when a specific component caused the
    navigation (the common case); Pantalla navega_a Pantalla directly
    when `get_edges`' own `component` field is empty - a whole-page
    redirect isn't attributable to one element. Never emitted toward a
    page absent from @graph.
    Details: docs/dev/generators/graph_export.md#_populate_navega_a
    """
    for edge in edges:
        if edge["to"] not in pantallas:
            continue
        source = (
            componentes.get(component_id(edge["from"], edge["component"]))
            if edge["component"]
            else pantallas.get(edge["from"])
        )
        if source is not None:
            _add_edge(source, "navega_a", edge["to"])


def _populate_dispara_and_consume(pantallas: Dict[str, Node], componentes: Dict[str, Node], inferred_requests: Iterable[Any]) -> None:
    """Componente dispara Endpoint for every component whose interaction
    triggered a call; Pantalla consume Endpoint for a call the page's own
    load fired with no component involved - InferredRequest's own
    triggered_by/loaded_by split (docs/dev/core/data_contracts.md), kept
    apart for the same reason it is there: "called when you open /orders"
    and "called when you click Save" are different facts.
    Details: docs/dev/generators/graph_export.md#_populate_dispara_and_consume
    """
    for request in inferred_requests:
        node_id = f"{request.method} {request.endpoint}"
        for page_url, path in request.triggered_by:
            source = componentes.get(component_id(page_url, path))
            if source is not None:
                _add_edge(source, "dispara", node_id)
        for page_url in request.loaded_by:
            source = pantallas.get(page_url)
            if source is not None:
                _add_edge(source, "consume", node_id)


def build_export_graph(request: DocumentRequest) -> Dict[str, Any]:
    """The full `export.json` payload: populated `Pantalla`/`Componente`/
    `Endpoint`/`Token`/`Modulo`/`Entidad`/`Requisito` nodes plus the
    edges connecting them, read fresh from the graph store every run -
    see `get_inferred_requests`' own docstring for why there is nothing
    here that can go stale between crawl passes.
    Details: docs/dev/generators/graph_export.md#build_export_graph
    """
    store = request.graph_store
    pages = store.get_progress_table_rows()
    component_ledger = store.get_component_ledger()
    inferred_requests = store.get_inferred_requests()

    pantallas = _pantalla_nodes(pages, store.get_page_titles(), store.get_page_descriptions())
    componentes = _componente_nodes(component_ledger)
    endpoints = _endpoint_nodes(inferred_requests)
    tokens = _token_nodes(build_tokens_document(store))
    root = route_shape(request.settings.get("target", "")) or None
    modulos = _modulo_nodes(pantallas, root)
    entidades = _entidad_nodes(build_data_model_document(request), endpoints)
    requisitos = _requisito_nodes(build_requirements_document(request), pantallas, endpoints, entidades)

    _populate_contiene(pantallas, component_ledger)
    _populate_navega_a(pantallas, componentes, store.get_edges())
    _populate_dispara_and_consume(pantallas, componentes, inferred_requests)

    graph = sorted(
        (
            *pantallas.values(), *componentes.values(), *endpoints.values(), *tokens.values(),
            *modulos.values(), *entidades.values(), *requisitos.values(),
        ),
        key=lambda node: (node["type"], node["id"]),
    )
    return {
        "@context": "./export.context.jsonld",
        "run_id": request.settings.get("run_id", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "@graph": graph,
    }


@DOCUMENT_REGISTRY.register("export")
class GraphExportDocument(DocumentGenerator):
    """Pipeline adapter for `build_export_graph`.
    Details: docs/dev/generators/graph_export.md#graphexportdocument
    """

    name = "export"
    title = "Graph Export"
    purpose = "The crawl graph as JSON-LD - screens, components, and endpoints, and how they connect - for tooling that would otherwise re-query the store."
    extension = "json"

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_export_graph(request)
        validate_against_schema(document, _SCHEMA_PATH)
        content = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        return (DocumentOutput(filename="export", kind="source", extension="json", content=content),)
