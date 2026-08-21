# Pipeline placement and dynamic-engine interact-once behavior

Resolves [Decide pipeline placement and dynamic-engine interact-once behavior](https://github.com/ezequielrickert/pragma/issues/135),
the last design ticket on [Component matching: embedding-based dedup and family grouping](https://github.com/ezequielrickert/pragma/issues/127).

## Placement: replaces `pragma cluster`'s implementation, not a new phase

`core/cluster_engine.py::ClusterEngine.run()` currently calls `analysis/
component_clustering.py::apply_component_families` — a post-hoc pass that reads every
component `pragma static` wrote, groups them (Jaccard, `generators/component_family.py`),
narrates each group, and writes `ComponentFamily`/`VARIANT_OF` back. No node mutation, nothing
re-crawled.

That's structurally the same slot this whole map's pipeline needs — read what `static` wrote,
write derived state back, don't re-crawl. Since the map's founding decision already established
that `component_family.py` gets *replaced*, not extended, the new pipeline **is** `pragma
cluster`'s new implementation. Running the new matching alongside the old one as a fifth phase
would leave two competing sources of `ComponentFamily` truth; there's no case where both should
run.

Within that replaced pass, four steps in order:

1. **Leaf exact collapse** — pairwise leaf-vector cosine similarity ([#131](https://github.com/ezequielrickert/pragma/issues/131)),
   union-find components scoring ≥ `leaf_exact` into equivalence classes, merge each class into
   one canonical `Component` row (per [#134](https://github.com/ezequielrickert/pragma/issues/134)'s
   literal-row-merge design), repointing `HAS_COMPONENT` and every other referencing edge.
2. **Leaf family grouping** — over the now-deduplicated component set, group components scoring
   ≥ `leaf_family` into `ComponentFamily`/`VARIANT_OF`, same shape as today just sourced from
   the new vector instead of Jaccard.
3. **Composite exact collapse** — bucket-then-bipartite-match `Container` roots
   ([#132](https://github.com/ezequielrickert/pragma/issues/132)), using the leaf vectors of the
   *already-canonical* children from step 1 (composite matching has to run after leaf collapse,
   or it would be comparing children that are about to be merged out from under it). Composites
   clearing `composite_exact` with full child coverage merge into one canonical `Container`.
4. **Composite family grouping** — the remainder, scoring ≥ `composite_family`, into
   `CompositeFamily`/`COMPOSITE_VARIANT_OF`.

## Dynamic engine: `FamilySampler`'s role narrows, doesn't disappear

Once a component is exact-collapsed, there's exactly one `Component` row — `Component.interacted`/
`interaction_count` (untouched by #134's schema change) go from being a per-page-instance fact
to a genuinely global one, for free, purely as a consequence of collapse. No sampler is needed
to enforce "interact once, ever" on the exact tier: the interact sweep checks the same flag it
already checks today, before acting on any component, and it's now correctly answering the
right question.

`analysis/family_sampling.py::FamilySampler` keeps its current sample-and-skip-the-rest behavior
**unchanged in spirit** for the family tier — family members are genuinely different objects,
worth sampling more than one of to see behavioral variation, exactly as `DEFAULT_MAX_SAMPLES_
PER_FAMILY = 3` already reflects. What changes mechanically: `_index_family_members` needs to
resolve against the new `ComponentFamily` records (sourced from the embedding pipeline) instead
of Jaccard-built ones, and its `component_identity()`-based lookup (built to survive a live DOM
selector churning across page reloads) needs reconciling with the new canonical component id —
an implementation detail for whoever builds this, not a design fork.

## Closing the loop: inferring behavior across every page a canonical component appears on

This is the concrete mechanism behind the map's founding navbar example — "any navigation of
the navbar only needs to be run one time, as any other behaviour is duplicated." After
interacting with a canonical exact-tier component once (via whichever page the interact sweep
reaches it on first) and observing its effect — most commonly a `NAVIGATES_TO` edge — write the
equivalent edge for **every other page** connected to that same canonical component via
`HAS_COMPONENT`, without re-running the interaction on any of them.

This is sound, not a guess, specifically because the exact tier already requires `href` and
every other action-governing field to be identical across every instance (#131's identity-string
block, weight 0.8, part of what "exact reuse" means by construction) — so the outcome genuinely
is the same action everywhere the canonical component appears. A family-tier component doesn't
get this treatment: its members are only *similar*, not asserted identical, so each one still
gets its own real interaction.

## What this leaves for implementation, not this map

Two mechanical questions surfaced while writing this up that don't change any decision already
made, just need resolving in code: how the equivalent-`NAVIGATES_TO` writes get tagged as
inferred-vs-directly-observed for any consumer that cares about the distinction (the schema has
no existing field built for this — `DERIVED_FROM` connects nodes, not edges, so it doesn't
directly apply to a `NAVIGATES_TO` fact), and the `component_identity()` reconciliation noted
above. Both are implementation-tickets territory once this map's design phase closes.
