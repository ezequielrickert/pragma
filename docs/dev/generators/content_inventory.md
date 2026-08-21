# `generators/content_inventory.py`

## module

`content-inventory.json` - copy/microcopy/legal text, one entry per
component instance where text was observed, docs/adr/0025.

**Why recompute `catalog_for`, not read `custom-elements.json`.**
`x-observed-variants` entries don't carry the raw observed text
(`CatalogVariant.example_text` lives only on the pre-serialization
dataclass) - `component_catalog.catalog_for` is the one real source, the
same one `custom_elements.py` itself serializes, with the identical
`variant-<N>` numbering so `component_ref` always resolves to the exact
entry a reader would find in `custom-elements.json`.

## _is_legal

A small, stated keyword table (`_LEGAL_KEYWORDS`) - the same
"field-name heuristic, not a language model's judgment call" shape
`data_model.py`'s own PII detection already uses (ADR-0008). A false
positive costs a human a few seconds of review; a false negative ships
unreviewed legal copy - the table is deliberately generous.

## _glossary_ref

`glossary.py`'s own `.strip().lower()` normalization, applied
identically here, matched against a real `glossary.jsonld` term set
built by calling `build_glossary_document` directly - never a second,
independently-derived hash. `None` (not an empty string) when this
text isn't a known term, matching this map's own null-for-absence
convention (`glossary.py`'s `axtree_ref`).

## _glossary_labels

`{normalized_prefLabel: TERM-<hash>}`, built once per document build and
reused for every entry's own lookup - not one `build_glossary_document`
call per catalog variant.

## build_content_inventory

One entry per catalog variant that actually carried text - a variant
with no `example_text` (an icon-only button, say) contributes nothing;
inventing empty copy would misrepresent what the crawl observed.

## _render_content_inventory_view

Mechanically rendered from `content-inventory.json`'s own entries -
never hand-authored in parallel with it.

## ContentInventoryDocument

Source (`content-inventory.json`, schema-validated) + view
(`content-inventory.md`) split, matching every other multi-file document
in this map.
