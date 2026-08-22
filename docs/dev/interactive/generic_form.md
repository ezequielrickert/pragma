# `interactive/generic_form.py`

## module

ADR-0034's schema-driven form (ticket #158) - `GENERIC_FORM_SPECS` names which fields are
HITL-fillable (a small, hand-maintained allowlist; there's no schema-level signal for that), but
each field's widget comes from that document's real JSON Schema, not a second hand-picked table.

Only `requirements.json` is a real entry today - a correction to ADR-0034 found while implementing
it: `browser-support-matrix.json`'s own generator always raises `NotImplementedError` (registered
only so `manifest.json` can carry it as `status: "off"`, ADR-0018/ADR-0027), so no real crawl ever
produces that document. `business_reason` stays real HITL language for a future case, not a live
one - see ADR-0034's own "Update" callout.

Does not retire `interactive/token_form.py` - `tokens.json`'s own recursive `group` shape needs
depth-capped `$ref` recursion this ticket's one real, flat document never needs. Building that
now, with no second case to prove it against, would be exactly the speculative generality
ADR-0034 argued against for the allowlist's own mechanism.

## GenericFormSpec

One document's own shape: `array_path` (`None` when the document's own root is the array; a
property name when it's nested, e.g. `requirements.json`'s `{"requirements": [...]}` wrapper),
`hitl_fields` (the allowlist itself), `summary_fields` (read-only context per row, so a reviewer
isn't editing `hitl_status` blind).

## Widget

A field's rendered input - `SELECT`/`TEXTAREA`/`TEXT` - resolved from its own schema construct
(`_widget_for`), never hand-picked per field name.

## FormField

One HITL-fillable field, already resolved to its real widget and current value -
`interactive/pages.py` renders this without needing to know anything about JSON Schema itself.

## FormEntry

One row of the repeatable array - `summary` is read-only context (never editable, never submitted
back), `fields` are this row's own `FormField`s.

## has_generic_form

Whether `filename` has a real, non-empty `GENERIC_FORM_SPECS` entry - `False` means no panel
renders at all, same as `token_form.py::color_tokens` returning `{}`.

## _entry_schema

The schema for one row - resolves the one level of `$ref` `requirements.schema.json`'s own
`items` uses (`{"$ref": "#/$defs/requirement"}`); a document whose `items` names its row shape
inline (no `$ref`) resolves directly, no recursion needed for either real shape.

## _widget_for

`enum` present → `SELECT`; `array` of `string` items → `TEXTAREA`; everything else → `TEXT`.
Schema-driven, not a per-field lookup table - a new allowlisted field gets its widget for free.

## _is_nullable

`"null"` present in the field's own `type` list - decides whether an empty submitted value saves
as `None` (nullable) or `""` (not).

## _ResolvedForm

`form_entries` and `save_generic_form` both need the same three things before they can do their
own real job - the spec, the parsed document, and the row's own field schemas. `_resolve` bundles
them so neither function repeats the other's guard-and-load logic.

## _resolve

`None` for exactly the three reasons a generic form can't exist here: no `GenericFormSpec` for
this filename, this site never produced the document, or (shouldn't happen for anything actually
in `GENERIC_FORM_SPECS`, but checked anyway) no known schema path.

## form_entries

Every row of `ref`'s array, each with its own HITL-fillable `FormField`s resolved against `ref`'s
real schema. `[]` when this site never produced `ref`, or `ref` has no `GenericFormSpec` - callers
should check `has_generic_form` first, but this degrades safely either way.

## save_generic_form

Patches `{row index: {field name: submitted value}}` into the effective document and saves
through the exact same `save_customized` every other edit uses - no new write or validation path.
A stale index or an unlisted field name (someone crafting a form key by hand) is silently ignored,
never a crash and never a write to a field outside the allowlist - the same "don't invent a new
token" boundary `token_form.py::save_color_tokens` already draws.
