# analysis/component_matching_pipeline.py

## module

The component-matching pipeline - issue #135's design, run against a real
graph store for the first time (issue #139): leaf exact collapse, leaf
family grouping, composite exact collapse, composite family grouping, in
that order. Replaces `analysis/component_clustering.py::
apply_component_families` outright, per the map's founding decision that
`generators/component_family.py`'s Jaccard clustering gets replaced, not
extended - there is no case where both should run.

`apply_component_matching` is the one entry point, called from
`core/cluster_engine.py` (`pragma cluster`) and `core/engine.py` (the
fused crawl+analyze run) - the same two call sites `apply_component_
families` used to have.

## apply_component_matching

Runs the whole four-step pipeline once, over whatever the graph store
currently holds.

## _leaf_merge_groups

`(canonical_id, [absorbed_id, ...])` per exact-tier cluster - bucketed by
`(tag, component_type)`, then union-find over pairwise leaf-vector cosine
similarity `>= threshold` within each bucket. The canonical row is
whichever cluster member sorts first by `(page_url, path)`.

## _build_leaf_families

`ComponentFamily` per family-tier cluster - same bucketing/union-find
shape as `_leaf_merge_groups`, at `thresholds.leaf_family` instead, run
*after* exact collapse so every cluster is a genuine "similar, not
identical" grouping.

## _dedup_composite_roots

`{id: ContainerNode}` deduplicated across every page, plus `{id:
[(page_url, path), ...]}` - a canonical `Container` root shared by
several pages appears once per page in the raw forest read, not a copy
worth re-comparing against itself, so matching runs against the
deduplicated set while family membership still needs every page it
actually renders on.

## _composite_merge_groups

`(canonical_id, [absorbed_id, ...])` per exact-tier composite cluster -
candidate pairs from `composite_matching.py::bucket_candidates`, scored
via `composite_score`, unioned only when `classify_composite_match`
reaches the given tier.

## _build_composite_families

`CompositeFamily` per family-tier composite cluster - same shape as
`_composite_merge_groups`, but every cluster with 2+ members becomes a
family instead of a merge, coverage gap or not, per #132's family-tier
rule.
