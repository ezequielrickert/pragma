"""`glossary.jsonld` - SKOS/JSON-LD domain vocabulary, `TERM-<hash>` ids,
docs/adr/0020.

**Term source: `data-model.json`'s own field names, scoped to
recurrence.** A field name declared on two or more distinct entities
(`email` on both `Customer` and `Order`, say) is real, deterministic
evidence it names a shared domain concept, not a one-off label - the
"recurs across contexts" test ADR-0020 point 3 sets. A field declared on
exactly one entity isn't promoted to a term: nothing here observed it
recurring, and inventing a concept from a single occurrence would be
exactly the kind of guess this pipeline's whole "never invent, state the
gap" discipline exists to avoid. Free-text component/page copy is a
plausible second source (a v2 could mine it for repeated business terms
too) but stays out of this ticket's scope - `data-model.json`'s fields
are already structured, low-noise vocabulary, where free text is not.

**`skos:broader`/`narrower`/`related` stay reserved (empty).** Two field
names alone carry no hierarchy signal pragma can honestly derive - SKOS's
own native relationship vocabulary is used as-is once a real signal
exists to populate it (a future ticket's concern), never populated from
a guess now.

**Cross-references, not duplication** (ADR-0020 point 3): a term cites
`"<Entity>.<field>"` pointers into `data-model.json` rather than copying
that field's own detail - the same "cite by pointer" discipline
`catalog.json`'s `x-tokens` already applies to `tokens.json` (ADR-0006).

**Evidence stays reserved too**: `derived_from` (no stable per-
interaction/HAR/screenshot id scheme exists yet, the same gap every
other document in this map left reserved) and `axtree_ref` (no
field-to-AXTree-leaf correlation pass exists, the same gap
`catalog.json`'s own `x-region.axtree_ref` left reserved, ticket #101).

Details: docs/dev/generators/glossary.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .data_model import build_data_model_document

_SCHEMA_PATH = "schemas/glossary.schema.json"

# SKOS's own real, long-established namespace - not one of this
# pipeline's own schema-locked "https://pragma.local/..." identifiers,
# the same "use the spec's real context string" convention
# usability.earl.jsonld's "https://www.w3.org/ns/earl" already set.
_SKOS_CONTEXT = "http://www.w3.org/2004/02/skos/core#"


def _normalize_label(label: str) -> str:
    """The identity-defining string `term_id` hashes - lowercase and
    stripped, so `"Email"` observed on one entity and `"email"` on
    another mint the same concept rather than two.
    Details: docs/dev/generators/glossary.md#_normalize_label
    """
    return label.strip().lower()


def term_id(label: str) -> str:
    """`TERM-<hash>` (ADR-0020 point 1) - a deterministic hash of the
    term's normalized `prefLabel`.
    Details: docs/dev/generators/glossary.md#term_id
    """
    return f"TERM-{short_hash(_normalize_label(label))}"


def _field_occurrences(data_model_document: Dict[str, Any]) -> Dict[str, List[str]]:
    """`{field_name: [entity_name, ...]}` for every field declared
    anywhere in `data-model.json`, sorted - the recurrence count this
    module promotes a field name to a term from.
    Details: docs/dev/generators/glossary.md#_field_occurrences
    """
    occurrences: Dict[str, List[str]] = {}
    for entity_name, entity in data_model_document["entities"].items():
        for field_name in entity["fields"]:
            occurrences.setdefault(field_name, []).append(entity_name)
    return {field_name: sorted(entities) for field_name, entities in occurrences.items()}


def _concept(field_name: str, entities: List[str]) -> Dict[str, Any]:
    return {
        "@id": term_id(field_name),
        "@type": "Concept",
        "prefLabel": field_name,
        "broader": [],
        "narrower": [],
        "related": [],
        "cross_references": [f"{entity}.{field_name}" for entity in entities],
        # Reserved: no stable per-interaction/HAR/screenshot id scheme
        # exists yet (the same gap prd/usability/accessibility/flows left
        # reserved).
        "derived_from": [],
        # Reserved: no field-to-AXTree-leaf correlation pass exists yet
        # (the same gap catalog.json's own x-region.axtree_ref left
        # reserved, ticket #101).
        "axtree_ref": None,
    }


def build_glossary_document(request: DocumentRequest) -> Dict[str, Any]:
    """`glossary.jsonld` - one `skos:Concept` per data-model field name
    that recurs across two or more entities.
    Details: docs/dev/generators/glossary.md#build_glossary_document
    """
    data_model_document = build_data_model_document(request)
    occurrences = _field_occurrences(data_model_document)
    concepts = [
        _concept(field_name, entities)
        for field_name, entities in sorted(occurrences.items())
        if len(entities) >= 2
    ]
    return {"@context": _SKOS_CONTEXT, "@graph": concepts}


def _render_glossary_view(document: Dict[str, Any], site: str) -> str:
    """`glossary.md` - mechanically rendered from `glossary.jsonld`,
    never hand-authored in parallel with it.
    Details: docs/dev/generators/glossary.md#_render_glossary_view
    """
    lines = [f"# Glossary: {site}", ""]
    concepts = document["@graph"]
    if not concepts:
        lines.append(
            "No recurring domain term was found. Read that narrowly: a term is only promoted here "
            "once the same data-model field name recurs across two or more entities - a genuinely "
            "small data model, or one whose forms happen to share no field names, produces no "
            "entries without that meaning the site itself has no domain vocabulary."
        )
        return "\n".join(lines) + "\n"

    lines += [
        f"{len(concepts)} recurring term(s), each citing the data-model fields it was observed as.",
        "",
        "| Term | Cross-references |",
        "|---|---|",
    ]
    lines += [
        f"| {concept['prefLabel']} | {', '.join(concept['cross_references'])} |"
        for concept in concepts
    ]
    lines.append("")
    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("glossary")
class GlossaryDocument(DocumentGenerator):
    """`glossary.jsonld` (source, schema-validated) and `glossary.md`
    (view) - docs/adr/0020.
    Details: docs/dev/generators/glossary.md#glossarydocument
    """

    name = "glossary"
    title = "Glossary"
    purpose = "Recurring domain vocabulary as a SKOS concept scheme, cross-referencing the data-model fields each term was observed as."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_glossary_document(request)
        validate_against_schema(document, _SCHEMA_PATH)
        view = _render_glossary_view(document, request.site)
        return (
            DocumentOutput(filename="glossary", kind="source", extension="jsonld", content=_as_json(document)),
            DocumentOutput(filename="glossary", kind="view", extension="md", content=view),
        )
