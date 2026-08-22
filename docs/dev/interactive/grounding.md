# `interactive/grounding.py`

## module

Real grounding facts for the interactive dashboard's chat, per ADR-0032's tiered model - never
invented, always traced to `export.json`'s own graph or another already-generated document's own
real citation field, both already on disk (the interactive server has no live graph-store
connection, ticket #151).

**Tier A** (`export.json`'s graph): `tokens`/`custom-elements` - both cite a `Token` by its real
DTCG alias. `custom-elements.json`'s own `x-tokens.color` already carries that alias literally in
its serialized JSON - no need to reconstruct it from `CatalogEntry`, which isn't recoverable from
the file alone (the page/path instances a catalog entry groups, `CatalogEntry.member_paths`, never
gets serialized into `custom-elements.json` itself). `tokens.json`'s own dot-path token ids are
re-derived with `generators/graph_export.py::token_nodes` (promoted public for this) - the exact
function `export.json`'s own `Token` nodes come from, so a token id computed here always matches a
real `export.json` node id, never a second, independently-derived one. Both resolve against
`export.json`'s own `usa_token` edges (ticket #126) - reversed, since this module asks "what uses
this token", not "what does this token use".

**Tier B** (another document's own citation field): `risk-register` (`service`, a plain string
naming one of `architecture.cyclonedx.json`'s own `externalServices` - not `service_ref` as
ADR-0032 first said; corrected there and here while implementing this ticket) and
`content-inventory` (`component_ref`/`screens`).

**Tier C** (honest nothing): every other document today - `data-model`, `requirements`/`prd`,
`architecture`'s own CALM/`Modulo` side, `change-log`, `decisions.adr`, and anything with no entry
in `_GROUNDING_BY_FILENAME` - real future work ticket #152 didn't cover in this first pass, not
silently promised. Extending to more document types is straightforward given this module's own
dispatch shape; each one just needs its own real citation field or graph-node mapping worked out
the same way the four here were.

## GroundingFact

One real, citable fact - always traced to `export.json`'s graph or another document's own real
field, never inferred.

## _load_json

The effective (customized-if-present) content of a document, parsed - `None` when it was never
produced for this site, so every `_*_grounding` function degrades to an empty list rather than
raising on a site that hasn't generated that document yet.

## _usa_token_citers

Every node id whose own `usa_token` edge names a given token - the reverse of ticket #126's own
edge direction (`Componente usa_token Token`), since grounding asks "what uses this", not "what
does this use".

## grounding_for

The dispatch entry point - `_GROUNDING_BY_FILENAME.get(ref.filename)`, `[]` for a document with no
entry yet (tier c). Mirrors `customization.py::SCHEMA_PATH_BY_FILENAME`'s own "absent means not
yet extended, not an error" shape.
