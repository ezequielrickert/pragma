# analysis/union_find.py

## module

Minimal union-find (disjoint-set) - shared by every clustering step in
`component_matching_pipeline.py` (leaf exact/family, composite
exact/family) that needs to turn a set of pairwise "these two belong
together" verdicts into groups. Single-linkage, same tradeoff the retired
`generators/component_family.py` Jaccard clustering made for the same
reason: a helpful grouping, not a guarantee every pair within it clears
the threshold directly.

## UnionFind

Standard `find`/`union` disjoint-set, indexed `0..size-1`.

## groups

Every current set, as a list of member indices - `find`'s result grouped
back into the sets it partitions `0..size-1` into.
