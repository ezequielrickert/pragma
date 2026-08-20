# `generators/custom_elements.py`

## module

`custom-elements.json` + `catalog.md`, per docs/adr/0006 - the Custom
Elements Manifest (CEM) serialization of `component_catalog.py`'s pure
inference, folding in the retired `catalog-data.json`.

**What "custom element" means here, honestly.** Pragma catalogues DOM
patterns the crawl grouped into families, not necessarily real,
registered Web Components. `customElement` is only ever `true` when the
tag itself carries the hyphenated custom-element naming convention
(`<my-button>`); every ordinary HTML tag is described as a regular class
declaration rather than every pattern being claimed as a real custom
element it may not be.

## _variant_declaration

One `x-observed-variants` entry (ADR-0006 point 2). `triggers`/`evidence`
are reserved: pragma has no stable per-interaction id scheme yet
(`CONTEXT.md`'s Short hash entry names seven, none of them an
interaction) - real ids here would be invented, not derived.

## _x_region

ADR-0006 point 3. Only `screen_id` is real - one of the pages this
pattern appears on, not necessarily the one a particular landmark match
came from (`build_catalog`'s own `_regions_of` already collapses to
distinct landmark names, not a per-page pairing). `landmark_path`/
`aria_role`/`axtree_ref` are reserved: correlating one catalog entry to
one specific `tree.axtree.json` node needs a second, dedicated
correlation pass this ticket doesn't build. Omitted entirely (not a
reserved-but-present object) when the entry has no known screen at all.

## _color_token_alias_by_value

`{hex_value: "{core.color.name}"}` for every core color token - what
`_x_tokens` matches a variant's own `background_color` against, after
`_normalized_hex` puts both sides in the same form.

## _normalized_hex

`CatalogVariant.background_color` carries the raw computed CSS string
(`"rgb(45, 119, 55)"`); `tokens.json`'s own color values are already
hex-normalized (`to_hex`, `design_tokens.py::_color_tokens`) - matching
the two requires putting them in the same form first. A real bug this
module's own tests caught: the first version compared the raw string
directly and never matched anything.

## _x_tokens

ADR-0006 point 4: DTCG alias citations, not copied values - a reader
follows `{core.color.surface-1}` into `tokens.json` rather than trusting
a second, possibly-stale copy of the hex code. `spacing` stays reserved:
`tokens.json` mints no spacing tokens (docs/adr/0005's own absence,
`design_tokens.py`'s `_ABSENT_NOTE`).

## _declaration

One CEM class declaration, plus pragma's three `x-` extensions.

## build_custom_elements_document

The full `custom-elements.json` payload: one synthetic module per catalog
entry, since pragma observes DOM patterns, not real module files - `path`
says so (`"observed/<Name>"`) rather than inventing a source location
that doesn't exist.

## _render_catalog_view

`catalog.md` - mechanically rendered from `custom-elements.json`, never
hand-authored in parallel with it.

## CustomElementsDocument

`custom-elements.json` (source, CEM-validated against
`schemas/custom-elements.schema.json`) and `catalog.md` (view) - folds in
the retired `catalog-data.json`. Registered as `"catalog"`, the same name
`component_catalog.py`'s own retired `ComponentCatalogDocument` used, so
no config or run history has to change to keep working.
