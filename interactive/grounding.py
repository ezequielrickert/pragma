"""Real grounding facts for the interactive dashboard's chat, per
ADR-0032's tiered model - never invented, always traced to
`export.json`'s own graph or another already-generated document's own
real citation field, both already on disk (the interactive server has
no live graph-store connection, ticket #151).

Per-document edit chat calls `grounding_for` + `system_instruction_for`
for the document open in the editor. The persistent global chat (ADR-
0035, ticket #179) routes first with `select_grounding_documents`, then
aggregates via `grounding_for_documents` + `system_instruction_for_global`.

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
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from dashboard.document_context import context_for
from generators.graph_export import token_nodes

from .customization import DocumentRef, SiteOutput, available_documents, effective_content


@dataclass(frozen=True)
class GroundingFact:
    """One real, citable fact for the chat's own `system_instruction` -
    always traced to `export.json`'s graph or another document's own
    real field, never inferred.
    Details: docs/dev/interactive/grounding.md#groundingfact
    """

    statement: str


@dataclass(frozen=True)
class SourcedGroundingFact:
    """A grounding fact plus the document it came from - so global chat
    can cite and link without auto-navigating (ADR-0035).
    Details: docs/dev/interactive/grounding.md#sourcedgroundingfact
    """

    source: DocumentRef
    statement: str


# Filename -> `document_context.py` registry name. Explicit, not guessed.
_FILENAME_REGISTRY_ALIASES: Dict[str, str] = {
    "custom-elements": "catalog",
    "catalog": "catalog",
    "flows.xstate": "flows",
    "flows.arazzo": "flows",
    "tree.aria": "tree",
    "tree.axtree": "tree",
    "accessibility-rules": "accessibility",
    "accessibility.earl": "accessibility",
    "accessibility.sarif": "accessibility",
    "usability-rules": "usability",
    "usability.earl": "usability",
    "usability.sarif": "usability",
    "architecture.calm": "architecture",
    "architecture.cyclonedx": "architecture",
    "openapi.raw": "openapi",
}

_ROUTING_TOKEN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)


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


def _registry_name(ref: DocumentRef) -> str:
    return _FILENAME_REGISTRY_ALIASES.get(ref.filename, ref.filename)


def _routing_tokens(ref: DocumentRef) -> set[str]:
    """Tokens a user message might match against this document."""
    tokens = {ref.filename.lower(), _registry_name(ref).lower()}
    tokens.update(part for part in ref.filename.replace(".", "-").split("-") if len(part) >= 3)
    context = context_for(_registry_name(ref))
    if context is not None:
        tokens.update(match.group(0).lower() for match in _ROUTING_TOKEN.finditer(context.explanation))
    return tokens


def _routing_score(message: str, ref: DocumentRef) -> int:
    message_tokens = {match.group(0).lower() for match in _ROUTING_TOKEN.finditer(message)}
    if not message_tokens:
        return 0
    doc_tokens = _routing_tokens(ref)
    overlap = len(message_tokens & doc_tokens)
    if ref.filename.lower() in message.lower():
        overlap += 2
    return overlap


def select_grounding_documents(
    where: SiteOutput,
    message: str,
    *,
    context_ref: Optional[DocumentRef] = None,
    limit: int = 3,
) -> List[DocumentRef]:
    """Up to `limit` produced documents whose grounding handlers should
    run this turn (ADR-0035) - deterministic token overlap, never a
    blind aggregate of every handler.
    Details: docs/dev/interactive/grounding.md#select_grounding_documents
    """
    produced = available_documents(where)
    if not produced:
        return []
    scored = sorted(
        ((ref, _routing_score(message, ref)) for ref in produced),
        key=lambda item: (-item[1], item[0].filename, item[0].extension),
    )
    selected: List[DocumentRef] = []
    if context_ref is not None and context_ref in produced:
        selected.append(context_ref)
    for ref, score in scored:
        if score <= 0 or ref in selected:
            continue
        selected.append(ref)
        if len(selected) >= limit:
            break
    return selected[:limit]


def grounding_for_documents(where: SiteOutput, refs: Sequence[DocumentRef]) -> List[SourcedGroundingFact]:
    """Real facts from each selected document, each tagged with its
    source - the global chat's grounding input (ADR-0035).
    Details: docs/dev/interactive/grounding.md#grounding_for_documents
    """
    facts: List[SourcedGroundingFact] = []
    for ref in refs:
        for fact in grounding_for(where, ref):
            facts.append(SourcedGroundingFact(source=ref, statement=fact.statement))
    return facts


_STANDING_INSTRUCTION = (
    "You are helping someone edit {filename}.{extension} for a site this crawl already "
    "documented. Guide them through the change rather than just executing it: point out real "
    "risks or tradeoffs when you can, but only ever cite a fact listed below - never invent a "
    "consequence you can't point to. If nothing is listed, say plainly that no real dependency "
    "data exists for this edit; don't guess."
)


def system_instruction_for(ref: DocumentRef, facts: List[GroundingFact]) -> str:
    """The chat's own `system_instruction` (ADR-0033 point 4) - the same
    standing guidance every turn, plus whichever grounding facts apply
    to `ref` right now. Built fresh per call, never cached: grounding is
    a property of what's being edited, not of the conversation's own
    history.
    Details: docs/dev/interactive/grounding.md#system_instruction_for
    """
    header = _STANDING_INSTRUCTION.format(filename=ref.filename, extension=ref.extension)
    if not facts:
        return f"{header}\n\nNo real grounding facts are available for this document."
    bullet_list = "\n".join(f"- {fact.statement}" for fact in facts)
    return f"{header}\n\nReal facts you can cite:\n{bullet_list}"


_GLOBAL_STANDING_INSTRUCTION = (
    "You are helping someone review documents from a site this crawl already documented. "
    "Answer their question using only the real facts listed below - never invent a "
    "consequence or dependency you can't point to. When a fact comes from a specific "
    "document and that document is relevant to your answer, name it and include the path "
    "`/document/{filename}.{extension}` so they can open it themselves - never assume the "
    "browser will navigate there for them. If no facts are listed, say plainly that no "
    "real dependency data exists for this question; don't guess."
)


def system_instruction_for_global(
    refs: Sequence[DocumentRef],
    facts: Sequence[SourcedGroundingFact],
) -> str:
    """Standing instruction for the persistent global chat panel
    (ADR-0035) - Q&A across routed documents, not edit guidance for one.
    Details: docs/dev/interactive/grounding.md#system_instruction_for_global
    """
    if not refs:
        return (
            f"{_GLOBAL_STANDING_INSTRUCTION}\n\n"
            "No documents were selected for grounding this turn."
        )
    doc_list = ", ".join(f"{ref.filename}.{ref.extension}" for ref in refs)
    header = f"{_GLOBAL_STANDING_INSTRUCTION}\n\nDocuments considered this turn: {doc_list}."
    if not facts:
        return f"{header}\n\nNo real grounding facts are available for those documents."
    bullet_list = "\n".join(
        f"- [{fact.source.filename}.{fact.source.extension}] {fact.statement}" for fact in facts
    )
    return f"{header}\n\nReal facts you can cite:\n{bullet_list}"
