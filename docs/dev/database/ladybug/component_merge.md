# database/ladybug/component_merge.py

## module

Literal-row-merge collapse for `Component` - issue #134's "collapse is a
literal row merge, not a pointer layer" decision, made real: once the
matching pipeline (issue #139) decides several `Component` rows are the
same exact-tier reuse, this is what actually makes them one row again.

**Copy the edges, then `DETACH DELETE` the absorbed node** - not "repoint
in place", which Cypher/Kùzu has no operation for. Every edge table where
`Component` is the `FROM` or `TO` side gets its own copy step; `DETACH
DELETE` at the end removes the absorbed node and every original edge
still pointing at it in one step.

`VARIANT_OF` is deliberately not handled: per #135's pipeline ordering,
exact collapse always runs before family grouping, so no `VARIANT_OF`
edge can exist on an about-to-be-absorbed `Component` yet.

## _ladybugcomponentmergemixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## merge_components

Collapses each `(canonical_id, [absorbed_id, ...])` group into one row -
every edge touching an absorbed id copies onto the canonical one
(preserving that edge table's own properties), the absorbed rows are
deleted, and `interacted`/`interaction_count` on every canonical row is
recomputed from its own (now-merged) `PERFORMED` edges - the union of
what canonical and every absorbed row separately knew.
