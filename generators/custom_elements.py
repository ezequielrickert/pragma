"""`custom-elements.json` + `catalog.md`, per docs/adr/0006 - the Custom
Elements Manifest (CEM) serialization of `component_catalog.py`'s pure
inference, folding in the retired `catalog-data.json`.

**What "custom element" means here, honestly.** Pragma catalogues DOM
*patterns* the crawl grouped into families - `<button>`, `<a>`, a
component-library `<div>` - not necessarily real, registered Web
Components. `customElement` is only ever `true` when the tag itself
carries the hyphenated custom-element naming convention (`<my-button>`);
every ordinary HTML tag is described as a regular class declaration, per
CEM's own schema, rather than every pattern being claimed as a real
custom element it may not be.

Details: docs/dev/generators/custom_elements.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .color_space import parse_css_color, to_hex
from .component_catalog import CatalogEntry, catalog_for
from .design_tokens import build_tokens_document

_SCHEMA_PATH = "schemas/custom-elements.schema.json"
# ADR-0006 names the CEM standard but not a version; 2.1.0 is the schema
# every field this module emits (declarations, attributes, custom
# extensions) is valid against.
_SCHEMA_VERSION = "2.1.0"


def _variant_declaration(index: int, variant: Any, screen_ids: Tuple[str, ...]) -> Dict[str, Any]:
    """One `x-observed-variants` entry (ADR-0006 point 2). `triggers`/
    `evidence` are reserved: pragma has no stable per-interaction id
    scheme yet (`CONTEXT.md`'s Short hash entry names seven, none of them
    an interaction) - real ids here would be invented, not derived.
    Details: docs/dev/generators/custom_elements.md#_variant_declaration
    """
    attributes: Dict[str, Any] = {}
    if variant.modifiers:
        attributes["class"] = " ".join(variant.modifiers)
    return {
        "variant_id": f"variant-{index}",
        "attributes": attributes,
        "screens": list(screen_ids),
        "triggers": [],
        "evidence": [],
    }


def _screen_ids(entry: CatalogEntry) -> Tuple[str, ...]:
    return tuple(f"SCR-{short_hash(page_url)}" for page_url in entry.used_on)


def _x_region(entry: CatalogEntry) -> Optional[Dict[str, Any]]:
    """ADR-0006 point 3. Only `screen_id` is real - one of the pages this
    pattern appears on, not necessarily the one a particular landmark
    match came from (`build_catalog`'s own `_regions_of` already collapses
    to distinct landmark names, not a per-page pairing). `landmark_path`/
    `aria_role`/`axtree_ref` are reserved: correlating one catalog entry
    to one specific `tree.axtree.json` node needs a second, dedicated
    correlation pass this ticket doesn't build. Omitted entirely (not a
    reserved-but-present object) when the entry has no known screen at
    all.
    Details: docs/dev/generators/custom_elements.md#_x_region
    """
    screen_ids = _screen_ids(entry)
    if not screen_ids:
        return None
    return {
        "screen_id": screen_ids[0],
        "landmark_path": None,
        "aria_role": None,
        "axtree_ref": None,
    }


def color_token_alias_by_value(tokens_document: Dict[str, Any]) -> Dict[str, str]:
    """`{hex_value: "{core.color.name}"}` for every core color token -
    what `x_tokens` matches a variant's own `background_color` against.
    Public (not `_`-prefixed): `generators/graph_export.py` reuses this
    exact function to derive `usa_token`'s own edges (ADR-0002/0005/0006,
    ticket #126), never a second, independently-derived alias table.
    Details: docs/dev/generators/custom_elements.md#color_token_alias_by_value
    """
    return {
        token["$value"]: f"{{core.color.{name}}}"
        for name, token in tokens_document.get("core", {}).get("color", {}).items()
    }


def _normalized_hex(css_color: str) -> Optional[str]:
    """`CatalogVariant.background_color` carries the raw computed CSS
    string (`"rgb(45, 119, 55)"`); `tokens.json`'s own color values are
    already hex-normalized (`to_hex`, `design_tokens.py::_color_tokens`)
    - matching the two requires putting them in the same form first.
    Details: docs/dev/generators/custom_elements.md#_normalized_hex
    """
    rgb = parse_css_color(css_color)
    return to_hex(rgb) if rgb else None


def x_tokens(entry: CatalogEntry, alias_by_value: Dict[str, str]) -> Dict[str, List[str]]:
    """ADR-0006 point 4: DTCG alias citations, not copied values - a
    reader follows `{core.color.surface-1}` into `tokens.json` rather
    than trusting a second, possibly-stale copy of the hex code.
    `spacing` stays reserved: `tokens.json` mints no spacing tokens
    (docs/adr/0005's own absence, `design_tokens.py`'s `_ABSENT_NOTE`).
    Public (not `_`-prefixed): `generators/graph_export.py` reuses this
    exact function for `usa_token`'s own edges (ticket #126) - the same
    alias citations, never a second, independently-derived computation.
    Details: docs/dev/generators/custom_elements.md#x_tokens
    """
    aliases = sorted({
        alias_by_value[hex_value]
        for variant in entry.variants
        if (hex_value := _normalized_hex(variant.background_color)) in alias_by_value
    })
    tokens: Dict[str, List[str]] = {"spacing": []}
    if aliases:
        tokens["color"] = aliases
    return tokens


def _attributes(entry: CatalogEntry) -> List[Dict[str, Any]]:
    return [
        {"name": prop.name, "type": {"text": prop.kind}, "description": f"Example: {prop.example}"}
        for prop in entry.props
    ]


def _declaration(entry: CatalogEntry, alias_by_value: Dict[str, str]) -> Dict[str, Any]:
    """One CEM class declaration, plus pragma's three `x-` extensions.
    Details: docs/dev/generators/custom_elements.md#_declaration
    """
    is_custom_element = "-" in entry.tag
    declaration: Dict[str, Any] = {
        "kind": "class",
        "name": entry.name,
        "description": entry.purpose,
        "customElement": is_custom_element,
        "attributes": _attributes(entry),
        "x-observed-variants": [
            _variant_declaration(index, variant, _screen_ids(entry))
            for index, variant in enumerate(entry.variants, 1)
        ],
        "x-tokens": x_tokens(entry, alias_by_value),
    }
    if is_custom_element:
        declaration["tagName"] = entry.tag
    region = _x_region(entry)
    if region is not None:
        declaration["x-region"] = region
    return declaration


def build_custom_elements_document(request: DocumentRequest) -> Dict[str, Any]:
    """The full `custom-elements.json` payload: one synthetic module per
    catalog entry, since pragma observes DOM patterns, not real module
    files - `path` says so (`"observed/<Name>"`) rather than inventing a
    source location that doesn't exist.
    Details: docs/dev/generators/custom_elements.md#build_custom_elements_document
    """
    entries = catalog_for(request)
    alias_by_value = color_token_alias_by_value(build_tokens_document(request.graph_store))
    modules = [
        {
            "kind": "javascript-module",
            "path": f"observed/{entry.name}",
            "declarations": [_declaration(entry, alias_by_value)],
            "exports": [],
        }
        for entry in entries
    ]
    return {"schemaVersion": _SCHEMA_VERSION, "readme": "", "modules": modules}


def _render_declaration(declaration: Dict[str, Any]) -> List[str]:
    lines = [f"## {declaration['name']}", ""]
    if declaration.get("description"):
        lines += [declaration["description"], ""]
    identity = [f"`<{declaration['tagName']}>`" if declaration.get("tagName") else "not a registered custom element"]
    lines += [" · ".join(identity), ""]

    if declaration["attributes"]:
        lines += ["| Attribute | Type | Description |", "|---|---|---|"]
        lines += [
            f"| `{a['name']}` | {a['type']['text']} | {a['description']} |" for a in declaration["attributes"]
        ]
        lines.append("")

    variants = declaration["x-observed-variants"]
    if len(variants) > 1:
        lines += ["**Variants**", "", "| Variant | Class | Screens |", "|---|---|---|"]
        lines += [
            f"| `{v['variant_id']}` | {v['attributes'].get('class', '(none)')} | "
            f"{', '.join(v['screens']) or '-'} |"
            for v in variants
        ]
        lines.append("")

    region = declaration.get("x-region")
    if region:
        lines += [f"Appears on: {region['screen_id']}.", ""]

    tokens = declaration.get("x-tokens") or {}
    if tokens.get("color"):
        lines += [f"Uses tokens: {', '.join(tokens['color'])}.", ""]
    return lines


def _render_catalog_view(document: Dict[str, Any], site: str) -> str:
    """`catalog.md` - mechanically rendered from `custom-elements.json`,
    never hand-authored in parallel with it.
    Details: docs/dev/generators/custom_elements.md#_render_catalog_view
    """
    declarations = [module["declarations"][0] for module in document["modules"]]
    lines = [f"# Component Catalogue: {site}", ""]
    if not declarations:
        lines.append("No reusable component patterns were inferred from this crawl.")
        return "\n".join(lines) + "\n"
    lines += [
        "Grouped by inferred pattern, largest first. `hover`, `focus` and `active` states are "
        "absent: the crawl only ever observes components at rest.",
        "",
    ]
    for declaration in declarations:
        lines += _render_declaration(declaration)
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("catalog")
class CustomElementsDocument(DocumentGenerator):
    """`custom-elements.json` (source, CEM-validated) and `catalog.md`
    (view) - folds in the retired `catalog-data.json`, docs/adr/0006.
    Details: docs/dev/generators/custom_elements.md#customelementsdocument
    """

    name = "catalog"
    title = "Component Catalogue"
    purpose = (
        "Every reusable component with its props, variants and where it is used, as a Custom "
        "Elements Manifest - the input for rebuilding the UI."
    )

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_custom_elements_document(request)
        validate_against_schema(document, _SCHEMA_PATH)
        source = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        view = _render_catalog_view(document, request.site)
        return (
            DocumentOutput(filename="custom-elements", kind="source", extension="json", content=source),
            DocumentOutput(filename="catalog", kind="view", extension="md", content=view),
        )
