# Generic form renderer: a per-document, per-field HITL allowlist, not depth or an allowlisted document set

**Status**: accepted

[Phase 2's first slice](https://github.com/ezequielrickert/pragma/issues/154) built one hand-written
form (`interactive/token_form.py`, a color picker for `tokens.json`'s `core.color` tokens) and
proved the shape: a form panel reading/writing through `interactive/customization.py`'s
`effective_content`/`save_customized`, coexisting with the raw-text editor rather than replacing
it. [This ticket](https://github.com/ezequielrickert/pragma/issues/156) designs the generic
version - driven by any document's own real JSON Schema, not a bespoke module per document.

Checked all 26 schema-backed documents (`SCHEMA_PATH_BY_FILENAME`) before deciding anything. Two
findings shaped every decision below: arrays-of-objects, keyed dicts (`additionalProperties`), and
recursive `$ref`s (`tokens.json`'s own `group` `$def` can nest a group inside a group indefinitely)
are all real and common - a "handle every JSON Schema construct" renderer is not a small problem.
And a real, already-established convention exists for "a field a human, not the pipeline, fills
in": `requirements.json`'s `hitl_status`/`open_questions` (ADR-0009) and
`browser-support-matrix.json`'s `business_reason`. Nothing else in any of the 26 schemas matched,
once each candidate was checked against its actual generator rather than just its schema
description - `confidence-summary`/`performance-baseline` are pure computed rollups,
`content-inventory.json`'s `requires_review` is a heuristic flag the pipeline sets, not a field a
human edits.

Decided:

**1. Editability is field-level, via a small hand-maintained allowlist of JSON-pointer paths - not
a depth ceiling and not a whole-document allowlist.** The two ideas collapse into one: a single
table, `{document filename: {json_pointer_path: widget}}`. A document with no entry gets no
generic-form panel at all (raw-text editor only, unchanged from today). Today's real table:

```
requirements:              hitl_status (enum), open_questions (array of strings)
browser-support-matrix:    business_reason (nullable string)
```

Every other field in an allowlisted document's own entries - `id`, `confidence`, `derived_from`,
`links`, `service`, `kind`, `subject`, `browserslist_query`, and so on - renders read-only, even
inside an otherwise-editable row. No schema-level signal distinguishes a HITL-fillable field from
a generated one (`hitl_status` is a plain enum like any other in the schema), so there's nothing
to introspect; a naming/shape heuristic (matching on the literal name `hitl_status`, or an enum
shape) risks silently making a generated field editable because it happens to share a name.
Cardinality is not the gate: `requirements.json` can have many entries, but each one has a real
editing task (review and approve it) - that's a different problem from `export.json`'s hundreds of
graph nodes with no editable field anywhere. The old "cardinality/depth ceiling" framing this
ticket started from was the wrong proxy; "does this field have a human-fillable entry in the
allowlist" is the real test, and it happens to exclude every graph/log-shaped document
(`export`, `glossary`, `evidence-log`, `change-log`, every `*.earl`/`*.sarif`, `architecture.*`,
`tree.*`) for the right reason - none of them have one - rather than by cardinality.

**2. `token_form.py` is retired.** `format: "color"` becomes one row in the widget-mapping table
below (`<input type="color">`), so `tokens.json`'s `core.color.*` no longer needs its own
hand-written module once the generic renderer covers the identical shape.

**3. Widget-mapping table** (used both for a leaf field type and for resolving a `$ref`'d shape):

| Schema construct | Widget |
|---|---|
| `string` | text input |
| `string`, `enum` | `<select>` |
| `boolean` | checkbox |
| `string`, `format: "color"` | `<input type="color">` |
| `array` of scalars | one `<textarea>`, one value per line |
| `array` of objects | repeatable fieldset, one per entry |
| `object` via `additionalProperties` (keyed dict) | repeatable "key + nested fields" row, add/remove by key |
| `$ref` to a recognized shape | recurse into a nested fieldset, capped at a small constant depth (independent of whether every level is "recognized" - `tokens.json`'s own recursive `group` `$def` is technically recognized at every level, so the cap exists purely to keep the rendered form usable) |
| anything else (`oneOf`/`anyOf`, an unrecognized `$ref`, conditional schemas) | falls back to the raw-text editor for that sub-tree - no attempt at full JSON Schema coverage |

**4. Coexists with the raw-text editor, unchanged from #154's own precedent.** The raw-text editor
is the one path that already handles everything the generic form declines (point 3's fallback
row), so it stays visible next to the generic form panel for every document, not just the
allowlisted ones.

**5. Add/remove a row (array-of-objects or keyed dict) is a real form submit - zero client-side
JS.** `interactive/pages.py` ships no `<script>` tag anywhere today; introducing this app's first
line of JS is a bigger threshold-cross than this ticket needs to make. A "+ add row" button POSTs
and re-renders the page with one more blank row/key appended, matching the all-forms-no-JS pattern
already established by every other route.

**6. Validation-error display is unchanged from today's raw-text path** - a failed save (a
required allowlisted field left blank, a value that fails the schema on the server-side
`jsonschema` check) shows the exact same whole-document `pages.validation_error_message`, not a
new per-field inline error. Richer per-field error display is
[a separate ticket's own question](https://github.com/ezequielrickert/pragma/issues/155), not this
one's.

**Consequence**: `CONTEXT.md` gained **HITL-fillable field** as a named concept - the allowlist
this ADR locks is that concept's first real, concrete instantiation. Building the actual renderer
(the widget table as code, the path-allowlist data structure, the add/remove-row routes) is
separate implementation work this ADR doesn't itself specify.
