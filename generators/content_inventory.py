"""`content-inventory.json` - copy/microcopy/legal text, one entry per
component instance where text was observed, docs/adr/0025.

**Granularity: component-primary, screen as location context** (point 1).
Entries cite the specific `catalog`/`custom-elements.json` component
variant a piece of text came from (`x-observed-variants`, ADR-0006) -
recomputed directly from `component_catalog.catalog_for`, the same raw
data `custom_elements.py` itself serializes, with the identical
`variant-<N>` numbering (`enumerate(entry.variants, 1)`) so
`component_ref` always resolves to the exact entry
`custom-elements.json` would show. Screens ride along for location
context, never as the primary organization - copy lives inside a
specific component, not a whole screen undifferentiated.

**`is_legal`/`requires_review`: this document's own flag, not DPV's**
(point 2). `data-model.json`'s DPV/PII annotations (ADR-0008) answer
whether a data *field's value* is personal data being collected; this
answers whether a piece of *static displayed copy* is legally-mandated
text - a different axis DPV was never built to describe. Detected the
same way `data-model.py`'s own PII field-name heuristic works: a small,
stated keyword table, not a language model's judgment call.
`requires_review` mirrors `is_legal` in v1 - no signal here can honestly
distinguish "legally mandated, needs a closer look" from "legally
mandated, obviously fine" with more confidence than "matched a legal
keyword at all."

**Completes `glossary`'s forward reference** (point 3, amending ADR-0020).
An entry whose own text normalizes to a real `glossary.jsonld` term's
`prefLabel` cites that term's `TERM-<hash>` back - recomputed via
`glossary.term_id` directly (never a second, independently-derived hash)
against `glossary.build_glossary_document`'s own real term set, so the
two documents can never silently disagree about which term ids exist.

Details: docs/dev/generators/content_inventory.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .component_catalog import CatalogEntry, catalog_for
from .glossary import build_glossary_document, term_id

_SCHEMA_PATH = "schemas/content-inventory.schema.json"

# A small, stated keyword table - the same "field-name heuristic, not an
# LLM judgment call" shape data_model.py's own PII detection already
# uses. Matched against normalized (lowercased) observed text; any hit
# is enough, since a false positive here costs a human a few seconds of
# review, while a false negative ships unreviewed legal copy.
_LEGAL_KEYWORDS: Tuple[str, ...] = (
    "terms of service", "terms and conditions", "terms & conditions", "privacy policy",
    "cookie policy", "all rights reserved", "disclaimer", "gdpr", "ccpa", "liability",
    "copyright", "©",
)


def _screen_id(page_url: str) -> str:
    return f"SCR-{short_hash(page_url)}"


def _is_legal(text: str) -> bool:
    """Details: docs/dev/generators/content_inventory.md#_is_legal"""
    normalized = text.lower()
    return any(keyword in normalized for keyword in _LEGAL_KEYWORDS)


def _glossary_ref(text: str, glossary_labels: Dict[str, str]) -> Any:
    """The matching `TERM-<hash>`, or `None` when this text isn't a known
    glossary term - `glossary.py`'s own normalization (`.strip().lower()`)
    applied identically here, so the same string matches regardless of
    which document normalized it first.
    Details: docs/dev/generators/content_inventory.md#_glossary_ref
    """
    normalized = text.strip().lower()
    return glossary_labels.get(normalized)


def _entries_for(entry: CatalogEntry, glossary_labels: Dict[str, str]) -> List[Dict[str, Any]]:
    screens = [_screen_id(page_url) for page_url in entry.used_on]
    entries = []
    for index, variant in enumerate(entry.variants, 1):
        if not variant.example_text:
            continue
        is_legal = _is_legal(variant.example_text)
        entries.append({
            "component_ref": f"{entry.name}#variant-{index}",
            "screens": screens,
            "text": variant.example_text,
            "is_legal": is_legal,
            "requires_review": is_legal,
            "glossary_ref": _glossary_ref(variant.example_text, glossary_labels),
        })
    return entries


def _glossary_labels(request: DocumentRequest) -> Dict[str, str]:
    """`{normalized_prefLabel: TERM-<hash>}` for every real
    `glossary.jsonld` term - built once, reused for every content-inventory
    entry's own lookup.
    Details: docs/dev/generators/content_inventory.md#_glossary_labels
    """
    glossary_document = build_glossary_document(request)
    return {
        concept["prefLabel"].strip().lower(): term_id(concept["prefLabel"])
        for concept in glossary_document["@graph"]
    }


def build_content_inventory(request: DocumentRequest) -> List[Dict[str, Any]]:
    """The full `content-inventory.json` payload: one entry per component
    variant with observed text, in catalog order.
    Details: docs/dev/generators/content_inventory.md#build_content_inventory
    """
    glossary_labels = _glossary_labels(request)
    entries: List[Dict[str, Any]] = []
    for entry in catalog_for(request):
        entries += _entries_for(entry, glossary_labels)
    return entries


def _render_content_inventory_view(entries: List[Dict[str, Any]]) -> str:
    """`content-inventory.md` - mechanically rendered from
    `content-inventory.json`, never hand-authored in parallel with it.
    Details: docs/dev/generators/content_inventory.md#_render_content_inventory_view
    """
    lines = ["# Content Inventory", ""]
    if not entries:
        lines.append("No component instance in this crawl carried observed text.")
        return "\n".join(lines) + "\n"

    legal_count = sum(1 for entry in entries if entry["is_legal"])
    lines += [
        f"{len(entries)} entr(ies), {legal_count} flagged as legally-mandated copy requiring review.",
        "",
        "| Component | Text | Legal | Glossary |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {entry['component_ref']} | {entry['text']} | {'yes' if entry['is_legal'] else 'no'} | "
        f"{entry['glossary_ref'] or '-'} |"
        for entry in entries
    ]
    lines.append("")
    return "\n".join(lines)


def _as_json(entries: List[Dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("content-inventory")
class ContentInventoryDocument(DocumentGenerator):
    """`content-inventory.json` (source, schema-validated) and
    `content-inventory.md` (view) - docs/adr/0025.
    Details: docs/dev/generators/content_inventory.md#contentinventorydocument
    """

    name = "content-inventory"
    title = "Content Inventory"
    purpose = "Copy, microcopy, and legally-mandated text, cited by the specific component instance it was observed on."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        entries = build_content_inventory(request)
        validate_against_schema(entries, _SCHEMA_PATH)
        view = _render_content_inventory_view(entries)
        return (
            DocumentOutput(filename="content-inventory", kind="source", extension="json", content=_as_json(entries)),
            DocumentOutput(filename="content-inventory", kind="view", extension="md", content=view),
        )
