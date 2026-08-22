"""Real grounding facts for the interactive dashboard's chat, per
ADR-0032's tiered model - never invented, always traced to
`export.json`'s own graph or another already-generated document's own
real citation field, both already on disk (the interactive server has
no live graph-store connection, ticket #151).

**Tier A** (`export.json`'s graph): `tokens`/`custom-elements` - both
cite a `Token` by its real DTCG alias. `custom-elements.json`'s own
`x-tokens.color` already carries that alias literally in its
serialized JSON (`generators/custom_elements.py::x_tokens`'s own
output) - no need to reconstruct it from `CatalogEntry`, which isn't
recoverable from the file alone (the page/path instances a catalog
entry groups, `CatalogEntry.member_paths`, never gets serialized into
`custom-elements.json` itself). `tokens.json`'s own dot-path token ids
are re-derived with `generators/graph_export.py::token_nodes` (promoted
public for this), the exact function `export.json`'s own `Token` nodes
come from - so a token id computed here always matches a real
`export.json` node id, never a second, independently-derived one.
Both resolve against `export.json`'s own `usa_token` edges (ticket
#126) - reversed, since this module asks "what uses this token", not
"what does this token use".

**Tier B** (another document's own citation field): `risk-register`
(`service`, a plain string naming one of `architecture.cyclonedx.json`'s
own `externalServices`) and `content-inventory` (`component_ref`/
`screens`).

**Tier C** (honest nothing): every other document today -
`data-model`, `requirements`/`prd`, `architecture`'s own CALM/`Modulo`
side, `change-log`, `decisions.adr`, and anything with no entry in
`_GROUNDING_BY_FILENAME` - real future work
[ticket #152](https://github.com/ezequielrickert/pragma/issues/152)
didn't cover in this first pass, not silently promised.

Details: docs/dev/interactive/grounding.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from generators.graph_export import token_nodes

from .customization import DocumentRef, SiteOutput, effective_content


@dataclass(frozen=True)
class GroundingFact:
    """One real, citable fact for the chat's own `system_instruction` -
    always traced to `export.json`'s graph or another document's own
    real field, never inferred.
    Details: docs/dev/interactive/grounding.md#groundingfact
    """

    statement: str


def _load_json(where: SiteOutput, ref: DocumentRef) -> Optional[Any]:
    """The effective (customized-if-present) content of `ref`, parsed -
    `None` when the document was never produced for this site.
    Details: docs/dev/interactive/grounding.md#_load_json
    """
    content = effective_content(where, ref)
    return json.loads(content) if content is not None else None


def _usa_token_citers(export_graph: Dict[str, Any], token_id: str) -> List[str]:
    """Every node id whose own `usa_token` edge names `token_id` - the
    reverse of ticket #126's own edge direction (Componente usa_token
    Token), since grounding asks "what uses this", not "what does this
    use".
    Details: docs/dev/interactive/grounding.md#_usa_token_citers
    """
    return sorted(
        node["id"] for node in export_graph.get("@graph", []) if token_id in node.get("usa_token", [])
    )


def _tokens_grounding(where: SiteOutput) -> List[GroundingFact]:
    tokens_document = _load_json(where, DocumentRef("tokens", "json"))
    export_graph = _load_json(where, DocumentRef("export", "json"))
    if tokens_document is None or export_graph is None:
        return []
    facts = []
    for token_id in sorted(token_nodes(tokens_document)):
        citers = _usa_token_citers(export_graph, token_id)
        if citers:
            facts.append(GroundingFact(f"Token '{token_id}' is used by: {', '.join(citers)}."))
    return facts


def _catalog_grounding(where: SiteOutput) -> List[GroundingFact]:
    document = _load_json(where, DocumentRef("custom-elements", "json"))
    if document is None:
        return []
    facts = []
    for module in document.get("modules", []):
        for declaration in module.get("declarations", []):
            name = declaration.get("name", "")
            for alias in declaration.get("x-tokens", {}).get("color", []):
                token_id = alias.strip("{}")
                facts.append(GroundingFact(f"Component '{name}' uses token '{token_id}'."))
    return facts


def _risk_register_grounding(where: SiteOutput) -> List[GroundingFact]:
    entries = _load_json(where, DocumentRef("risk-register", "json"))
    if entries is None:
        return []
    return [
        GroundingFact(f"Risk on service '{entry['service']}': {entry.get('description', entry.get('rule', ''))}")
        for entry in entries
    ]


def _content_inventory_grounding(where: SiteOutput) -> List[GroundingFact]:
    entries = _load_json(where, DocumentRef("content-inventory", "json"))
    if entries is None:
        return []
    return [
        GroundingFact(
            f"Text on component '{entry['component_ref']}' "
            f"(screens: {', '.join(entry.get('screens', [])) or 'none recorded'}): "
            f'"{entry.get("text", "")}"'
        )
        for entry in entries
    ]


_GROUNDING_BY_FILENAME: Dict[str, Callable[[SiteOutput], List[GroundingFact]]] = {
    "tokens": _tokens_grounding,
    "custom-elements": _catalog_grounding,
    "risk-register": _risk_register_grounding,
    "content-inventory": _content_inventory_grounding,
}


def grounding_for(where: SiteOutput, ref: DocumentRef) -> List[GroundingFact]:
    """Every real grounding fact for `ref` - `[]` (tier c, honest
    nothing) for a document `_GROUNDING_BY_FILENAME` has no entry for
    yet, never a fabricated one.
    Details: docs/dev/interactive/grounding.md#grounding_for
    """
    handler = _GROUNDING_BY_FILENAME.get(ref.filename)
    return handler(where) if handler else []
