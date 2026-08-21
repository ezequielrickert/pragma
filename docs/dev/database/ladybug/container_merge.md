# database/ladybug/container_merge.py

## module

Literal-row-merge collapse for `Container` - the same shape
`component_merge.py::merge_components` follows, over `Container`'s own
edges.

## _ladybugcontainermergemixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## merge_containers

Collapses each `(canonical_id, [absorbed_id, ...])` group into one
`Container` row - `HAS_CONTAINER`, and `CONTAINS` on both the containing
and the contained side, copy onto the canonical row; the absorbed rows are
then deleted. `COMPOSITE_VARIANT_OF`/`DERIVED_FROM(CompositeFamily ->
Container)` are not handled here for the same reason `component_merge.py`
skips `VARIANT_OF`: composite family grouping always runs after composite
exact collapse (#135), so neither edge can exist yet.
