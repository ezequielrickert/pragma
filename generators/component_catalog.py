"""D5: a catalogue of the components a site is built from, with their
props and variants - the pure inference logic `generators/custom_elements.py`
serializes as Custom Elements Manifest (docs/adr/0006).

Deliberately **not** the Atomic Design pyramid. Atoms, molecules,
organisms and templates draw a tidy diagram and feed nothing; what someone
rebuilding this application in React or Vue needs is, per component, its
props, its variants, and where it is used. The atomic level is reported
only where it can be determined from what was captured, and omitted rather
than guessed - see `research/plan-generacion-de-documentos.md` Fase 3.

Needs no new capture: families already exist
(`component_family.build_component_families`), and every prop below is a
`ComponentFacts` field the crawl has been persisting all along.

Split from its own `DocumentGenerator` (moved to `custom_elements.py`,
which owns `"catalog"`'s registration) since ticket #101: this module is
pure inference over the graph, unaware of CEM's own shape, the same
`build_X` / `DocumentGenerator`-adapter split every other generator here
uses.

Details: docs/dev/generators/component_catalog.md#module
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.documents import DocumentRequest
from core.interfaces import ComponentFamily
from .component_classifier import describe_options_from_rows, format_option_choices
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
    # The landmark regions this pattern's instances actually sit in
    # ("navigation", "main", "contentinfo", ...), sorted and deduplicated.
    # Empty when no instance is inside a landmark, and also empty for a
    # crawl recorded before containment capture existed - the document says
    # which, rather than leaving a reader to guess from a blank line.
    # Details: docs/dev/generators/component_catalog.md#regions
    regions: Tuple[str, ...] = ()
    # Every individual `(page_url, path)` component instance this entry
    # groups, sorted - `used_on` collapses these to distinct pages;
    # `graph_export.py::build_export_graph` needs the instances
    # themselves to wire `usa_token` onto each real `Componente` node,
    # not once per page. Added ticket #126, deferred out of #101 rather
    # than rushed into it.
    # Details: docs/dev/generators/component_catalog.md#member_paths
    member_paths: Tuple[Tuple[str, str], ...] = ()


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


def _with_option_labels(member: Dict[str, Any]) -> Dict[str, Any]:
    """`member` plus the `option_labels` prop, derived rather than read.

    The ledger carries a choice-group's options as `options` -
    `(rows, group_name)` straight off the `Option` table. It used to also
    carry `option_labels`, a pre-rendered list written alongside a JSON
    blob that no longer exists, and `_PROP_FIELDS` kept asking for that
    key: every dropdown and choice-group in this document lost its
    options at the migration, silently, because a missing prop is
    indistinguishable from a component that has none.

    Derived into a copy, never written onto the ledger entry itself -
    `flat_component_ledger`'s dicts are shared with every other generator
    in the run.
    Details: docs/dev/generators/component_catalog.md#_with_option_labels
    """
    labels = format_option_choices(describe_options_from_rows(*member.get("options", ([], ""))))
    return {**member, "option_labels": labels}


def _regions_of(members: Sequence[Dict[str, Any]], regions: Dict[str, Dict[str, str]]) -> Tuple[str, ...]:
    """The distinct landmark regions this family's instances sit in.

    A pattern used in both the navigation and the footer is a different
    thing from one used only in the footer, and that is a fact about the
    component worth putting next to its props.
    Details: docs/dev/generators/component_catalog.md#_regions_of
    """
    found = {
        regions.get(member.get("page_url", ""), {}).get(member.get("path", ""), "")
        for member in members
    }
    return tuple(sorted(region for region in found if region))


def build_catalog(
    families: Sequence[ComponentFamily],
    components: Sequence[Dict[str, Any]],
    regions: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[CatalogEntry]:
    """One `CatalogEntry` per inferred family, largest first.

    `regions` is `GraphStore.get_component_regions()`'s output. `None` and
    `{}` are treated alike here, but they mean different things to a
    reader - see `ComponentCatalogDocument.generate`, which is where the
    distinction is stated rather than silently rendered as "no regions".
    Details: docs/dev/generators/component_catalog.md#build_catalog
    """
    regions = regions or {}
    by_key = {(c.get("page_url"), c.get("path")): c for c in components}
    used_names: Dict[str, int] = {}
    entries = []

    for family in sorted(families, key=lambda f: (-len(f.member_paths), f.component_type)):
        members = [_with_option_labels(by_key[key]) for key in family.member_paths if key in by_key]
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
                regions=_regions_of(members, regions),
                member_paths=tuple(sorted((member.get("page_url", ""), member.get("path", "")) for member in members)),
            )
        )
    return entries


def catalog_for(request: DocumentRequest) -> List[CatalogEntry]:
    """The catalogue both documents below render, read once in one place.

    They used to carry byte-identical copies of these three store reads,
    which is how the prose document and the JSON document could drift into
    describing different catalogues.
    Details: docs/dev/generators/component_catalog.md#catalog_for
    """
    store = request.graph_store
    return build_catalog(
        store.get_component_families(),
        flat_component_ledger(store),
        store.get_component_regions(),
    )
