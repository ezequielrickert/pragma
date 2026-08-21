# Composite/subtree matching composition

Resolves [Design composite/subtree matching composition](https://github.com/ezequielrickert/pragma/issues/132),
child of [Component matching: embedding-based dedup and family grouping](https://github.com/ezequielrickert/pragma/issues/127).

Extends the leaf-level design
([#131](https://github.com/ezequielrickert/pragma/issues/131),
`docs/dev/generators/leaf-feature-vector-design.md`) and the algorithm survey
([#129](https://github.com/ezequielrickert/pragma/issues/129),
`docs/dev/generators/subtree-matching-research.md`) up to the `Container` level: how a `<nav>`
and its children get matched and scored as one unit across pages, without a new vector type.

## Shape: same one-pipeline-two-threshold philosophy, one level up

A composite's score is not a separate vector compared through Kùzu's vector index — it's a
pairwise computation over pre-bucketed candidate pairs (children counts and root shape can't be
searched with nearest-neighbor lookup the way a single leaf vector can). The steps:

1. **Bucket candidates cheaply.** Group `Container` roots by `(tag, component_type)`, then drop
   any pair whose child counts differ by more than 50% before doing any per-child work. This is
   the same discipline `component_family.py` already applies before its Jaccard pass — bucket
   first, compare only within a bucket.

2. **Score the root.** Compute the `Container` root's own vector using #131's exact encoding
   (`tag`, `role`, `css_class`, plus `landmark` folded into the structural block the same way
   `role` is) — `element_id` excluded, same precedent as leaf `Component`s. This is one term in
   the final average, not a separate gate.

3. **Match children via bipartite assignment.** For two composites' children (leaf `Component`s
   and/or nested `Container`s, see step 4), compute pairwise leaf-vector cosine similarity for
   every cross pair, then run an optimal bipartite assignment (Hungarian algorithm — cubic in a
   tiny n, composites are tens of children per #129's sizing, not hundreds) to find the best 1:1
   correspondence. This assignment *is* the child-to-child correspondence: whichever nav link on
   page A paired with whichever nav link on page B is exactly "which button leads where" staying
   individually addressable after the parent collapses.

4. **Recurse bottom-up for nested composites.** A `Container`'s child can itself be a `Container`
   with its own subtree. Compute and cache each `Container`'s composite score once; an ancestor
   composite's matching treats an already-scored child `Container` as a single comparable unit
   (its cached score stands in for it), rather than re-matching its descendants from scratch.

5. **Aggregate into one composite score** — coverage-weighted average over `{root term} ∪
   {matched child-pair terms}`:

   ```
   score = (root_similarity + sum(matched_pair_similarities)) / (1 + max(children_A, children_B))
   ```

   Unmatched children (count mismatch) aren't dropped from the denominator, so they pull the
   score down proportionally instead of being invisible to it. A single child with a
   page-specific class difference (e.g. an `"active"` nav-link marker) barely dents an otherwise-
   identical navbar's score, since it's one term among many, not a veto.

## Exact tier requires full coverage, not just a high score

The map's founding decision (#127) requires exact reuse to mean "the same object," not "a
close match." Differing child counts (5 nav links on one page, 6 with an extra conditional
"Admin" link on another) are the realistic reason a navbar's shape varies at all — that's a
genuinely different DOM shape, not the same node. So the two tiers are gated differently, not
just by threshold:

- **Exact/collapse tier**: requires `matched_count == children_A == children_B` (every child on
  both sides matched, nothing left over) **and** the coverage-weighted score clears the
  exact-tier threshold ([#133](https://github.com/ezequielrickert/pragma/issues/133)).
- **Family tier**: any score clearing the (lower) family threshold, coverage gap or not.

A composite with unmatched children is capped at family tier regardless of how high its
coverage-weighted score computes — the hard gate comes first, the threshold second.

## What this hands off

- Exact numeric thresholds for both tiers, and whether the 50%-child-count bucketing slack in
  step 1 needs tuning: [#133](https://github.com/ezequielrickert/pragma/issues/133).
- How a collapsed composite (canonical `Container` + canonical children, each still individually
  addressable per step 3's matching) is represented in the graph, and how
  `ComponentFamily`/`VARIANT_OF` relate to it: [#134](https://github.com/ezequielrickert/pragma/issues/134).
- Where this matching pass runs in the static→cluster→dynamic pipeline, and how the dynamic
  engine uses a collapsed composite's canonical children to interact once per child instead of
  once per page instance: [#135](https://github.com/ezequielrickert/pragma/issues/135).
