# Customization propagates by read-time resolution, not write-time patching

**Status**: accepted

[Interactive dashboard](https://github.com/ezequielrickert/pragma/issues/146)'s own charting
locked field-level override over regeneration-with-replaced-facts: a customized document is the
original's own shape with edited values, never a re-run of its generator fed fake facts - much
less invasive than giving every one of the ~26 generators an override mechanism. This ADR settles
the question that decision left open: when editing one document (say `tokens.json`'s
`core.color.surface-1`), how does everything that depends on the changed value stay consistent?

Confirmed against the actual code before deciding: this pipeline already cites, never copies, a
value across a document boundary. `custom-elements.json`'s own `x-tokens.color`
(`generators/custom_elements.py::x_tokens`) is a DTCG alias string (`"{core.color.surface-1}"`),
never the resolved hex value (ADR-0006 point 4's own "DTCG alias citations, not copied values").
`catalog.md`'s rendered "Uses tokens: {alias}." line cites the same alias, not the value.
`export.json`'s own `Token` node (`generators/graph_export.py::_walk_token_groups`) carries only
`id`/`type`/`label` - never `$value` - so the `usa_token` edge (ticket #126) points at a token's
identity, not a snapshot of what it was worth at export time. The same pattern holds for
`data_model.py`'s `_api_citations` (endpoint strings, not response bodies) and `evidence_log.py`'s
`interaction:<id>`/`har:<id>` citations (an id to resolve, never the captured payload inlined).

Decided:

**1. No write-time propagation for a cited value.** Editing `core.color.surface-1`'s `$value`
needs zero changes to `custom-elements.json`, `catalog.md`, or `export.json` - their own citations
of that token's *identity* are still correct after the edit; only what the identity currently
resolves to has changed. Propagation is a read-time concern: whatever resolves a citation (the
interactive dashboard's own UI, a future consumer) must resolve it against the *customized*
version of the cited document first, falling back to the original only when no customization
exists for that document. No new patch-forwarding logic between document pairs is needed for the
common case.

**2. A customized document is a complete, schema-valid copy, not a sparse overlay.**
The *entire* document, edited value(s) already substituted in - not a JSON Patch or a
`{path: new_value}` diff. This means `utils/schema_validation.py::validate_against_schema` applies
to a customized document exactly as it does to an original one, with no merge-then-validate step
to build first. The cost is per-site disk duplication of documents that get customized;
irrelevant next to a scraped site's own crawl data.

**Update - ticket #151, path convention corrected against the real layout**: this point
originally said `data/output/<slug>/customized/<same-filename>`, a per-site subdirectory that
doesn't match how `data/output/` actually works - every document lives flat, named
`{slug}_{filename}_{timestamp}.{extension}` (`generators/pipeline.py::DocumentNaming.path_for`),
never under a per-site subdirectory. A customized document follows the same flat convention, just
without the timestamp (it isn't a per-run artifact): `data/output/customized/
{slug}_{filename}.{extension}` - `slug` is `slugify(site)` (`utils/urls.py`), matching
`DocumentNaming`'s own slugging, not the raw site string `runs.json` happens to key by.

**3. No raw-value-copy case is known to exist today.** Every citation relationship checked while
charting this map cites by id/alias. If a real one turns up later (a document this ADR's authors
didn't check, or a new document a future ticket adds), *that* relationship needs its own explicit
re-derivation step when its cited document is customized - this ADR's read-time-resolution rule
doesn't cover a document that copied a value outright. Tracked as fog on
[Interactive dashboard](https://github.com/ezequielrickert/pragma/issues/146) until a concrete
instance is found, not solved speculatively here.

**Consequence**: whatever renders a document for the interactive dashboard needs one shared
"effective document for this site" lookup (`data/output/customized/{slug}_{filename}.{extension}`
if it exists, else the original) that every consumer goes through - not a per-document special
case. Designing that lookup, and how edits get written to `customized/` in the first place, is
separate implementation work this ADR doesn't itself specify.
