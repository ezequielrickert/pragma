"""D5: a catalogue of the components a site is built from, with their
props and variants.

Deliberately **not** the Atomic Design pyramid. Atoms, molecules,
organisms and templates draw a tidy diagram and feed nothing; what someone
rebuilding this application in React or Vue needs is, per component, its
props, its variants, and where it is used. The atomic level is reported
only where it can be determined from what was captured, and omitted rather
than guessed - see `research/plan-generacion-de-documentos.md` Fase 3.

Needs no new capture: families already exist
(`component_family.build_component_families`), and every prop below is a
`ComponentFacts` field the crawl has been persisting all along.

Details: docs/dev/generators/component_catalog.md#module
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.interfaces import ComponentFamily
from core.registry import DOCUMENT_REGISTRY
from .ledger import flat_component_ledger

# Ledger fields that describe a component's *interface* - what a rebuilt
# version would take as props. Style and geometry are deliberately absent:
# those belong to the design-token document (D10), not to this one.
# Details: docs/dev/generators/component_catalog.md#_prop_fields
_PROP_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("label", "string"),
    ("placeholder", "string"),
    ("name", "string"),
    ("href", "string"),
    ("form", "string"),
    ("required", "boolean"),
    ("disabled", "boolean"),
    ("option_labels", "list"),
)

# Tags whose elements are indivisible controls in their own right.
_ATOM_TAGS = frozenset({"button", "input", "a", "select", "textarea"})


@dataclass(frozen=True)
class CatalogProp:
    """One input a rebuilt component would take.
    Details: docs/dev/generators/component_catalog.md#catalogprop
    """

    name: str
    kind: str
    varies: bool
    example: str


@dataclass(frozen=True)
class CatalogVariant:
    """One visually distinct flavour of a component.
    Details: docs/dev/generators/component_catalog.md#catalogvariant
    """

    modifiers: Tuple[str, ...]
    background_color: str
    count: int
    example_text: str


@dataclass(frozen=True)
class CatalogEntry:
    """One component in the catalogue.
    Details: docs/dev/generators/component_catalog.md#catalogentry
    """

    name: str
    tag: str
    component_type: str
    purpose: str
    atomic_level: str
    member_count: int
    used_on: Tuple[str, ...]
    props: Tuple[CatalogProp, ...]
    variants: Tuple[CatalogVariant, ...]
    states_observed: Tuple[str, ...]


def component_name(component_type: str) -> str:
    """A PascalCase identifier from a classifier label.

    `"submit button"` -> `"SubmitButton"`, `"text field (email)"` ->
    `"TextFieldEmail"`, `"combobox (searchable dropdown)"` ->
    `"Combobox"`.

    A single-word parenthetical is kept because it discriminates
    (`email` vs `password` really are different components); a longer one
    is prose describing the same component and is dropped, which is what
    keeps `custom control (component-library element, no native tag/role)`
    from becoming an unreadable identifier.
    Details: docs/dev/generators/component_catalog.md#component_name
    """
    head, _, tail = component_type.partition("(")
    words = re.findall(r"[A-Za-z0-9]+", head)
    parenthetical = re.findall(r"[A-Za-z0-9]+", tail.rstrip(")"))
    if len(parenthetical) == 1:
        words += parenthetical
    return "".join(word[:1].upper() + word[1:] for word in words) or "Component"


def _extra_classes(css_class: str, common: Sequence[str]) -> Tuple[str, ...]:
    """A member's own CSS classes minus the ones its whole family shares."""
    return tuple(sorted(set(css_class.split()) - set(common)))


def _atomic_level(tag: str, members: List[Dict[str, Any]]) -> str:
    """`"atom"`, `"atom (in a form)"`, or `""` when it can't be told.

    Only two things in the captured data speak to composition: an
    indivisible HTML tag, and `facts.form`, which discovery already
    records via `el.closest('form')`. Container nesting beyond that would
    need the nearest landmark ancestor captured too - out of scope, and
    the field is omitted rather than guessed.
    Details: docs/dev/generators/component_catalog.md#_atomic_level
    """
    if tag not in _ATOM_TAGS:
        return ""
    in_form = all(member.get("form") for member in members)
    return "atom (in a form)" if in_form else "atom"


def _props(members: List[Dict[str, Any]]) -> Tuple[CatalogProp, ...]:
    """Every interface field at least one member actually carries."""
    props = []
    for field, kind in _PROP_FIELDS:
        values = [member.get(field) for member in members]
        present = [value for value in values if value not in ("", None, False, [])]
        if not present:
            continue
        distinct = {json.dumps(value, sort_keys=True) for value in values}
        example = present[0]
        props.append(
            CatalogProp(
                name=field,
                kind=kind,
                varies=len(distinct) > 1,
                example=", ".join(example) if isinstance(example, list) else str(example),
            )
        )
    return tuple(props)


def _variants(members: List[Dict[str, Any]], common_classes: Sequence[str]) -> Tuple[CatalogVariant, ...]:
    """Group members by what visually distinguishes them from their siblings.

    `common_classes` already holds what the whole family shares, so
    whatever is left on an individual member *is* the modifier - a
    primary/secondary pair differing only by a colour class comes out as
    two variants of one component rather than two components.
    Details: docs/dev/generators/component_catalog.md#_variants
    """
    grouped: Dict[Tuple[Tuple[str, ...], str], List[Dict[str, Any]]] = {}
    for member in members:
        key = (_extra_classes(member.get("css_class") or "", common_classes),
               member.get("background_color") or "")
        grouped.setdefault(key, []).append(member)

    variants = [
        CatalogVariant(
            modifiers=modifiers,
            background_color=background,
            count=len(group),
            example_text=next((m.get("text") or "" for m in group if m.get("text")), ""),
        )
        for (modifiers, background), group in grouped.items()
    ]
    return tuple(sorted(variants, key=lambda v: (-v.count, v.modifiers)))


def build_catalog(families: Sequence[ComponentFamily], components: Sequence[Dict[str, Any]]) -> List[CatalogEntry]:
    """One `CatalogEntry` per inferred family, largest first.
    Details: docs/dev/generators/component_catalog.md#build_catalog
    """
    by_key = {(c.get("page_url"), c.get("path")): c for c in components}
    used_names: Dict[str, int] = {}
    entries = []

    for family in sorted(families, key=lambda f: (-len(f.member_paths), f.component_type)):
        members = [by_key[key] for key in family.member_paths if key in by_key]
        if not members:
            continue
        name = component_name(family.component_type)
        used_names[name] = used_names.get(name, 0) + 1
        if used_names[name] > 1:
            name = f"{name}{used_names[name]}"
        entries.append(
            CatalogEntry(
                name=name,
                tag=family.tag,
                component_type=family.component_type,
                purpose=family.purpose,
                atomic_level=_atomic_level(family.tag, members),
                # Counted from the members actually resolved, not from
                # family.member_paths - a family can name a component the
                # ledger no longer has, and claiming "3 instances" while
                # describing two is the kind of quiet inconsistency that
                # makes a reader stop trusting the whole document.
                # Details: docs/dev/generators/component_catalog.md#member_count
                member_count=len(members),
                used_on=tuple(sorted({member.get("page_url", "") for member in members})),
                props=_props(members),
                variants=_variants(members, family.common_classes),
                states_observed=("disabled",) if any(m.get("disabled") for m in members) else (),
            )
        )
    return entries


def _render_entry(entry: CatalogEntry) -> List[str]:
    lines = [f"## {entry.name}", ""]
    if entry.purpose:
        lines += [entry.purpose, ""]
    plural = "instance" if entry.member_count == 1 else "instances"
    facts = [f"`<{entry.tag}>`", entry.component_type, f"{entry.member_count} {plural}"]
    if entry.atomic_level:
        facts.append(entry.atomic_level)
    lines += [" · ".join(facts), ""]

    if entry.props:
        lines += ["| Prop | Type | Varies | Example |", "|---|---|---|---|"]
        lines += [
            f"| `{p.name}` | {p.kind} | {'yes' if p.varies else 'no (same on every instance)'} | {p.example} |"
            for p in entry.props
        ]
        lines.append("")

    if len(entry.variants) > 1:
        lines += ["**Variants**", "", "| Modifier classes | Background | Instances | Example |", "|---|---|---|---|"]
        lines += [
            f"| {', '.join(v.modifiers) or '(none)'} | {v.background_color or '-'} | {v.count} | {v.example_text} |"
            for v in entry.variants
        ]
        lines.append("")

    lines += [f"Used on: {', '.join(entry.used_on)}", ""]
    if entry.states_observed:
        lines += [f"States observed: {', '.join(entry.states_observed)}.", ""]
    return lines


@DOCUMENT_REGISTRY.register("catalog")
class ComponentCatalogDocument(DocumentGenerator):
    """Details: docs/dev/generators/component_catalog.md#componentcatalogdocument"""

    name = "catalog"
    title = "Component Catalogue"
    purpose = "Every reusable component with its props, variants and where it is used - the input for rebuilding the UI."

    def generate(self, request: DocumentRequest) -> str:
        entries = build_catalog(
            request.graph_store.get_component_families(request.site),
            flat_component_ledger(request.graph_store, request.site),
        )
        lines = [f"# Component Catalogue: {request.site}", ""]
        if not entries:
            lines.append("No reusable component patterns were inferred from this crawl.")
            return "\n".join(lines) + "\n"
        lines += [
            "Grouped by inferred pattern, largest first. `hover`, `focus` and `active` states are "
            "absent: the crawl only ever observes components at rest.",
            "",
        ]
        for entry in entries:
            lines += _render_entry(entry)
        return "\n".join(lines)


@DOCUMENT_REGISTRY.register("catalog-data")
class ComponentCatalogData(DocumentGenerator):
    """The same catalogue as JSON, so a Storybook generator doesn't parse prose.
    Details: docs/dev/generators/component_catalog.md#componentcatalogdata
    """

    name = "catalog-data"
    title = "Component Catalogue (data)"
    purpose = "The component catalogue as structured JSON, for a design-system or Storybook generator."
    extension = "json"

    def generate(self, request: DocumentRequest) -> str:
        entries = build_catalog(
            request.graph_store.get_component_families(request.site),
            flat_component_ledger(request.graph_store, request.site),
        )
        payload = {"site": request.site, "components": [asdict(entry) for entry in entries]}
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
