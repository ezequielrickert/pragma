# `src/generators/component_family.py`

## module

Post-hoc, whole-site inference of reusable component "families" (a
Button pattern, a combobox pattern, ...) from components a crawl already
discovered - not part of the live per-page write path `GraphStoreSink`
drives during a crawl (see `src/core/engine.py::_apply_component_families`
for where this runs: once, after `MechanicalCrawler.crawl_site` finishes,
since clustering needs to see every discovered component across the
whole site at once).

Pure, no I/O, same placement discipline as `component_classifier.py` -
the impure read-from-`GraphStore`/write-back-to-`GraphStore` orchestration
lives in `engine.py`, not here.

## _similarity_threshold

Jaccard similarity floor (0.5), over `css_class` tokens, for two
same-`(tag, component_type)` components to count as variants of one
family. An earlier design pointedly considered weighting by class
rarity (TF-IDF-style, to suppress shared layout-utility classes like
`flex`/`rounded`) and rejected it: on a real Tailwind-styled button pair
differing only by a color modifier (`btn-primary` vs `btn-secondary`),
weighting *up* the rare, differentiating class is exactly wrong - it's
precisely the class the family is supposed to tolerate varying, not
treat as evidence of a different family. Plain (unweighted) Jaccard,
scoped strictly within a `(tag, component_type)` bucket first, avoids
that failure mode: the bucket boundary already does the heavy lifting a
weighting scheme would otherwise be trying to approximate.

## _min_family_size

A family needs at least 2 members - a component with no siblings isn't
a reusable pattern, it's just a component. The same bar
`tags_with_multiple_instances` uses for "is this tag common enough to
deserve its own label" - both are the same "at least one sibling"
reasoning, applied to two different questions.

## _class_tokens / _similarity

`_similarity` returns 1.0 when both class-token sets are empty (two
unstyled elements read as identical) and 0.0 when only one is - an
unstyled and a styled element are never the same family, regardless of
how few tokens the styled side has.

## _UnionFind / _cluster_bucket

Single-linkage clustering: any pair at or above the similarity
threshold gets merged, transitively. A chain of pairwise-similar
members can end up in one cluster even if its two most distant members
aren't directly similar to each other - accepted for this feature's
purpose (a helpful grouping for a migration PRD, not a database-critical
dedup). Revisit only if that chaining shows up as a real problem on a
real site, not preemptively.

## build_component_families

Buckets by `(tag, component_type)` first - nothing ever merges across
element kinds regardless of class overlap, which is what makes plain
(unweighted) Jaccard safe to use inside a bucket (see
`_similarity_threshold`'s own doc anchor). `common_classes` on each
returned `ComponentFamily` (`src/core/interfaces.py`) is the
intersection of every member's own classes - a human-readable summary
of what the family visually has in common. `member_paths` is sorted
before being returned, so a round-trip through either `GraphStore`
backend (`Neo4jGraphStore.get_component_families` has its own matching
`ORDER BY`) compares equal regardless of clustering/iteration order.

## _tag_label_overrides / label_for_tag

Human-readable, Cypher-label-safe name for a raw HTML tag - most tags
just capitalize (`button` -> `Button`); `<a>` reads as `Link` since the
bare letter `A` isn't a usable node label in practice. Falls back to
`"Component"` for anything that isn't a plain identifier (e.g. a custom
element like `<my-widget>`, whose hyphen isn't valid in an unescaped
Cypher label) - `Neo4jGraphStore.apply_tag_labels` bakes this string
directly into a Cypher query (labels can't be bound parameters), so
this function is the one place that guarantees every value it can
produce is safe to interpolate.

## tags_with_multiple_instances

Tags worth their own label - appearing on `_MIN_FAMILY_SIZE`+
components for the site. A tag seen only once has no "type" to speak of
yet, so it stays generic (`:Component`, no dynamic label added).
