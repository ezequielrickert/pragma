"""The generic, schema-driven form (ADR-0034, ticket #158) - unlike
`interactive/token_form.py`'s hand-written color picker, this module
never hard-codes a field's widget. `GENERIC_FORM_SPECS` names *which*
fields are HITL-fillable (ADR-0034's own field-level allowlist - there
is no schema-level signal for that, so this part stays hand-maintained
by design); everything past that - the widget each field gets, the
`enum` options a `<select>` offers - comes from that document's real
JSON Schema, not a second hand-picked table.

**Only `requirements.json` is a real case as of this ticket** - a
correction to ADR-0034, found while implementing it, not while
designing it: `browser-support-matrix.json`'s own generator
(`generators/browser_support_matrix.py::BrowserSupportMatrixDocument.
generate`) always raises `NotImplementedError` - it's registered only
so `manifest.json` can carry it as `status: "off"` (ADR-0018/ADR-0027's
"reserved, not live" posture), so no real crawl ever produces this
document at all. ADR-0034 checked the schema and the field's own HITL
language, not whether the generator producing it is actually live -
`business_reason` stays a real *field*, just not a real case *today*.
Adding it back once that generator ships for real is exactly the cheap
extension this mechanism exists for - one more `GENERIC_FORM_SPECS`
entry, no new machinery.

**Does not retire `interactive/token_form.py`.** ADR-0034 named that as
this ticket's destination, but `tokens.json`'s own shape (a `core.color`
tree with a recursive `group` `$def`) needs the depth-capped `$ref`
recursion ADR-0034's widget table describes - real, unbuilt machinery
this ticket's one real document (`requirements`, a flat array of
objects) never needs. Building that recursion now, with no real case to
prove it against, would be exactly the speculative generality ADR-0034
itself argued against for the allowlist's own mechanism. `token_form.py`
stays as its own special case until a real nested-shape document needs
the generic path too.

Details: docs/dev/interactive/generic_form.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .customization import DocumentRef, SiteOutput, effective_content, save_customized, schema_path_for

ENTRY_FIELD_PREFIX = "entry:"


class Widget(Enum):
    """A field's rendered input, derived from its own schema construct
    (ADR-0034's widget-mapping table) - never hand-picked per field
    name.
    Details: docs/dev/interactive/generic_form.md#widget
    """

    SELECT = "select"
    TEXTAREA = "textarea"
    TEXT = "text"


@dataclass(frozen=True)
class GenericFormSpec:
    """One document's own generic-form shape - the allowlist itself
    (`hitl_fields`) plus the two facts needed to locate the repeatable
    array and label each row, none of which any schema encodes:
    `array_path` (`None` when the document's own root is the array,
    e.g. `browser-support-matrix.json`; a property name when it's
    nested, e.g. `requirements.json`'s own `{"requirements": [...]}`
    wrapper) and `summary_fields` (read-only context shown per row, so
    a reviewer isn't editing `hitl_status` blind - e.g. `syntax_text`
    for a requirement).
    Details: docs/dev/interactive/generic_form.md#genericformspec
    """

    array_path: Optional[str]
    hitl_fields: List[str]
    summary_fields: List[str]


GENERIC_FORM_SPECS: Dict[str, GenericFormSpec] = {
    "requirements": GenericFormSpec(
        array_path="requirements",
        hitl_fields=["hitl_status", "open_questions"],
        summary_fields=["id", "syntax_text"],
    ),
    # "browser-support-matrix" deliberately absent - its own generator
    # always raises NotImplementedError (see module docstring); no real
    # document exists to build a form for yet.
}


@dataclass(frozen=True)
class FormField:
    """One HITL-fillable field, already resolved to its real widget and
    current value - `interactive/pages.py` renders this without
    needing to know anything about JSON Schema itself.
    Details: docs/dev/interactive/generic_form.md#formfield
    """

    name: str
    widget: Widget
    value: str
    options: List[str]


@dataclass(frozen=True)
class FormEntry:
    """One row of the repeatable array - `summary` is read-only context
    (never editable, never submitted back), `fields` are this row's own
    `FormField`s.
    Details: docs/dev/interactive/generic_form.md#formentry
    """

    index: int
    summary: str
    fields: List[FormField]


def has_generic_form(filename: str) -> bool:
    """Whether `filename` has a real, non-empty entry in
    `GENERIC_FORM_SPECS` - `False` means no generic-form panel renders
    at all, same as `interactive/token_form.py::color_tokens` returning
    `{}` for a document with no color tokens.
    Details: docs/dev/interactive/generic_form.md#has_generic_form
    """
    return filename in GENERIC_FORM_SPECS


def _load_schema(schema_path: str) -> Dict[str, Any]:
    loaded: Dict[str, Any] = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return loaded


def _entry_schema(schema: Dict[str, Any], spec: GenericFormSpec) -> Dict[str, Any]:
    """The schema for one row of `spec`'s array - resolves the one
    level of `$ref` `requirements.schema.json`'s own `items` uses
    (`{"$ref": "#/$defs/requirement"}`); `browser-support-matrix.
    schema.json` names its row shape inline under `items` directly, no
    `$ref` to follow.
    Details: docs/dev/interactive/generic_form.md#_entry_schema
    """
    array_schema = schema["properties"][spec.array_path] if spec.array_path else schema
    items = array_schema["items"]
    ref = items.get("$ref")
    resolved: Dict[str, Any] = schema["$defs"][ref.removeprefix("#/$defs/")] if ref else items
    return resolved


def _entries(document: Any, spec: GenericFormSpec) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = document[spec.array_path] if spec.array_path else document
    return entries


def _widget_for(field_schema: Dict[str, Any]) -> Widget:
    if "enum" in field_schema:
        return Widget.SELECT
    field_type = field_schema.get("type")
    types = field_type if isinstance(field_type, list) else [field_type]
    if "array" in types and field_schema.get("items", {}).get("type") == "string":
        return Widget.TEXTAREA
    return Widget.TEXT


def _is_nullable(field_schema: Dict[str, Any]) -> bool:
    field_type = field_schema.get("type")
    types = field_type if isinstance(field_type, list) else [field_type]
    return "null" in types


def _field_value(entry: Dict[str, Any], name: str, widget: Widget) -> str:
    raw = entry.get(name)
    if widget is Widget.TEXTAREA:
        return "\n".join(raw or [])
    return raw or ""


def _summary_for(entry: Dict[str, Any], spec: GenericFormSpec) -> str:
    return " - ".join(str(entry[name]) for name in spec.summary_fields if entry.get(name))


def _form_field(entry: Dict[str, Any], name: str, field_schema: Dict[str, Any]) -> FormField:
    widget = _widget_for(field_schema)
    return FormField(name=name, widget=widget, value=_field_value(entry, name, widget), options=field_schema.get("enum", []))


@dataclass(frozen=True)
class _ResolvedForm:
    """`form_entries` and `save_generic_form` both need the same three
    things before they can do their own real job - this is that shared
    resolution, not a second concept of its own.
    Details: docs/dev/interactive/generic_form.md#_resolvedform
    """

    spec: GenericFormSpec
    document: Any
    field_schemas: Dict[str, Dict[str, Any]]


def _resolve(where: SiteOutput, ref: DocumentRef) -> Optional[_ResolvedForm]:
    """`None` for exactly the three reasons a generic form can't exist
    here: no `GenericFormSpec` for `ref.filename`, this site never
    produced `ref`, or (shouldn't happen for anything actually in
    `GENERIC_FORM_SPECS`, but checked anyway) no known schema path.
    Details: docs/dev/interactive/generic_form.md#_resolve
    """
    spec = GENERIC_FORM_SPECS.get(ref.filename)
    content = effective_content(where, ref)
    schema_path = schema_path_for(ref.filename)
    if spec is None or content is None or schema_path is None:
        return None
    document = json.loads(content)
    entry_schema = _entry_schema(_load_schema(schema_path), spec)
    return _ResolvedForm(spec=spec, document=document, field_schemas=entry_schema["properties"])


def form_entries(where: SiteOutput, ref: DocumentRef) -> List[FormEntry]:
    """Every row of `ref`'s array, each with its own HITL-fillable
    `FormField`s resolved against `ref`'s real schema. `[]` when this
    site never produced `ref`, or `ref` has no `GenericFormSpec` at all
    (callers should check `has_generic_form` first; this still
    degrades safely either way).
    Details: docs/dev/interactive/generic_form.md#form_entries
    """
    resolved = _resolve(where, ref)
    if resolved is None:
        return []
    return [
        FormEntry(
            index=index,
            summary=_summary_for(entry, resolved.spec),
            fields=[_form_field(entry, name, resolved.field_schemas[name]) for name in resolved.spec.hitl_fields],
        )
        for index, entry in enumerate(_entries(resolved.document, resolved.spec))
    ]


def save_generic_form(where: SiteOutput, ref: DocumentRef, updates: Dict[int, Dict[str, str]]) -> None:
    """Patches `updates` (`{row index: {field name: submitted value}}`)
    into the effective document and saves through the exact same
    `save_customized` every other edit uses - no new write or
    validation path. A stale index (the document changed since the
    form was loaded) or an unlisted field name is ignored, not an
    error - the same "don't invent a new token" boundary
    `token_form.py::save_color_tokens` already draws.
    Details: docs/dev/interactive/generic_form.md#save_generic_form
    """
    resolved = _resolve(where, ref)
    if resolved is None:
        return
    entries = _entries(resolved.document, resolved.spec)
    for index, field_updates in updates.items():
        if not 0 <= index < len(entries):
            continue
        for field_name, raw_value in field_updates.items():
            if field_name not in resolved.spec.hitl_fields:
                continue
            field_schema = resolved.field_schemas[field_name]
            widget = _widget_for(field_schema)
            if widget is Widget.TEXTAREA:
                entries[index][field_name] = [line for line in raw_value.splitlines() if line.strip()]
            elif _is_nullable(field_schema):
                entries[index][field_name] = raw_value or None
            else:
                entries[index][field_name] = raw_value
    save_customized(where, ref, json.dumps(resolved.document, indent=2, ensure_ascii=False) + "\n")
