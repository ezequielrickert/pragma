# database/ladybug/composite_family.py

## module

Inferred-composite-family write/read path for `LadybugGraphStore` -
`CompositeFamily`'s counterpart to `component_family.py`'s `ComponentFamily`
handling, same shape, one level up.

## _resolve_container_ids

`{path: container_id}` for every given path with a `HAS_CONTAINER` edge on
this page already - `_component_lookup.py::resolve_component_ids`'s
counterpart for `Container`, kept local since this is its only caller.

## _ladybugcompositefamilymixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## record_composite_families

Replaces the site's entire inferred-composite-family structure - full
rebuild, same contract as `record_component_families`. `member_paths` is
`(page_url, path)`, resolved to a `Container` through its `HAS_CONTAINER`
edge; a pair that doesn't resolve to a real `Container` is silently
skipped.

## get_composite_families

Every inferred composite family currently recorded for the site - same
shape/reasoning as `get_component_families`, over
`COMPOSITE_VARIANT_OF`/`HAS_CONTAINER` instead of `VARIANT_OF`/
`HAS_COMPONENT`.
