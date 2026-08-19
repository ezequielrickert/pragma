# database/ladybug/component_family.py

## module

The inferred tier's `ComponentFamily` and its `VARIANT_OF` edges - a
deterministic cluster of `Component` nodes, the shape
`generators/component_family.py::build_component_families` produces.

Written by `Engine`'s post-crawl pass, **not** by `GraphStoreSink`. Clustering
needs to see every component in the site at once; the live per-page write
stream the crawl produces cannot supply that.

Unaffected by the API-contract redesign that replaced `RequestFamily` with
`Endpoint`: a component family is still a cluster over observations, so it
stayed a stored inference while the request side became a read-time
aggregation.

## _ladybugcomponentfamilymixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## record_component_families

Replaces the site's entire family structure - a full rebuild, not an
incremental merge, because cluster membership is not stable across runs. A
component added on the second crawl can legitimately move a family's
boundaries, and merging would leave both the old and the new shape in place.

**A `member_paths` entry that resolves to no `Component` is silently skipped**,
and that is confirmed engine behaviour rather than an assumption: a `MATCH`
inside an `UNWIND` drops that iteration, not the whole write. So a family
naming a component the ledger no longer has still lands with its remaining
members - which is also why `component_catalog.build_catalog` counts resolved
members rather than trusting `len(member_paths)`.

## get_component_families

Every family currently recorded. A family with zero resolved members produces
no row at all, since the `MATCH` requires at least one `VARIANT_OF` edge.

**Grouped inside the query (`WITH f, collect(...)`), not by a Python-side
key.** `id(f)` comes back as an unhashable dict (`{"table": ..., "offset":
...}`), confirmed against the real engine - so a naive
`dict.setdefault` keyed on it would raise, and keying on the family's
properties instead would silently collapse two distinct families that happen
to share every property. Cypher's own grouping distinguishes nodes by
identity and has neither problem.

The read reconstructs the same `ComponentFamily` shape `build_component_families`
emits, with `member_paths` sorted by an explicit `ORDER BY`, so a round-trip
through the store compares equal to what went in.
