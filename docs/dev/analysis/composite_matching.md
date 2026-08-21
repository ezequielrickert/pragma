# analysis/composite_matching.py

## module

Composite/subtree matching - issue #132's design, implemented as pure
functions over an in-memory `Container`/`Component` tree. No I/O, no graph
store - reading a live `CONTAINS` traversal into `ContainerNode`s and
wiring the result into the pipeline is issue #139's job.

`composite_score` is the module's one real entry point - a coverage-
weighted similarity between two composites, with the bipartite child-to-
child correspondence as a byproduct, not a separate computation.

## ContainerNode

One `Container` root or subtree. `children` mixes leaf component dicts and
nested `ContainerNode`s, matching what a `CONTAINS` traversal actually
returns. `id` only needs to be unique within one matching run - it is the
memoization key `composite_score` caches nested-composite results under.

## CompositeMatchResult

One pairwise composite comparison's full outcome - `score`, plus
`matched_pairs`/`root_similarity` for a caller that needs the *why*.

## container_root_vector

A `Container` root's own vector - `tag`/`role`/`landmark` hashed into the
structural block the same way a leaf's `tag`/`role` are (#131's encoding),
plus `css_class` as its own weighted slice. No style/geometry - a
`Container` carries none.

## bucket_candidates

Candidate pairs cheap enough to score - grouped by `(tag, role)` (a
`Container`'s closest analog to a leaf's `(tag, component_type)` bucket
key, since `Container` carries no `component_type` of its own), then any
pair whose child counts differ by more than `child_count_slack` of the
larger side is dropped before any per-child work runs.

## composite_score

The coverage-weighted composite score: `(root_similarity + sum(matched_pair_
similarities)) / (1 + max(children_a, children_b))`. Children are matched
via optimal bipartite assignment (`hungarian.py`); a `Container` child
recurses into this same function, memoized by `(id, id)`. A leaf can never
match a composite root. Unmatched children (a count mismatch) stay out of
the numerator but still count in the denominator.

## classify_composite_match

`"exact"`, `"family"`, or `"none"` - the tiers issue #132 defines, at the
thresholds issue #133 calibrated. Exact requires `result.full_coverage`
**and** a threshold, not a threshold alone.
