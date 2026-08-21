# Composite/subtree structural matching: algorithm survey

Research for issue [#129](https://github.com/ezequielrickert/pragma/issues/129), part of map
[#127](https://github.com/ezequielrickert/pragma/issues/127) (component matching: embedding-based
dedup and family grouping). Findings only — no implementation.

## Question

Survey established approaches to detecting and matching repeated composite substructures across a
set of trees (this project's `Container` + child-`Component` structures, one tree per page,
compared across pages), and recommend one approach (or a short list) suited to: (a) small-to-moderate
tree sizes, (b) near-matches (family tier) as well as exact matches (collapse tier), (c) composing
with the deterministic leaf-level feature vector another ticket on this map is designing, and (d)
staying dependency-light and explainable.

## What the schema actually gives an algorithm to work with

Read from `database/ladybug/schema.py` and `docs/dev/database/ladybug/schema.md` directly (not
inferred):

- **`Container`** (`id`, `path`, `tag`, `role`, `landmark`, `element_id`, `css_class`) and
  **`Component`** (`id`, `path`, `tag`, `text`, `role`, `input_type`, `visible`, `layer`, geometry,
  `component_type`, ledger fields, `ComponentFacts`) are separate node tables. A composite (e.g. a
  `<nav>`) is a `Container`; its children are `Component` and/or nested `Container` rows.
- **`CONTAINS`** is polymorphic: `Container -> Component` and `Container -> Container`, and it is
  declared **direct containment only**. `schema.md`: "the retired DuckDB backend stored the full
  transitive closure ... Ancestry beyond one hop is a `CONTAINS*` traversal" — there is no
  materialized ancestor list or depth column on either table today, and no sibling-order column
  either (Kùzu `REL TABLE` rows carry no implicit position).
- **`path`** (present on `Component`, `Container`, `TextContent`, `Option`) is described only as
  "the member's own original CSS selector" (`Option.path`'s doc, the most explicit phrasing in the
  file) — a per-node original-selector string, not a serialized tree position, and there is no
  guarantee two structurally identical subtrees on different pages share comparable `path` values
  (CSS selectors are page-specific by construction: `nav:nth-child(2) > ul` on one page may be
  `nav:nth-child(3) > ul` on another for the same reused navbar).
- **No ordering, no depth, no parent pointer on the node tables themselves.** Any tree-shaped
  algorithm (tree edit distance, canonical hashing, alignment) has to first reconstruct the tree
  in memory via `CONTAINS*` traversal per `Container` root, using `Component`/`Container` field
  values as node labels — the schema stores a graph a tree can be *read out of*, not a tree object.
- One composite tree today is bounded in size by one page's DOM component subtree under one
  `Container` root — small (tens, not thousands, of nodes per composite) per the map's own framing
  ("(a) small-to-moderate tree sizes (a single page's DOM component tree)").

This matters for the recommendation below: general-purpose tree algorithms from the literature
assume ordered, labeled trees with parent/child/sibling access in O(1); here that structure has to
be materialized from `CONTAINS*` first, and there is no native ordering to exploit or discard.

## Candidate approaches surveyed

**1. Tree edit distance (Zhang-Shasha, RTED, APTED).** Computes the minimum-cost sequence of
node insert/delete/relabel operations transforming one *ordered* labeled tree into another.
State of the art is APTED (Pawlik & Augsten, ACM TODS 40(1), 2015; *Tree edit distance: Robust and
memory-efficient*, Information Systems 56, 2016), which supersedes their own earlier RTED
(PVLDB 5(4), 2011) — both are O(n³) time / O(mn) space in the general case, worse than the earlier
Zhang-Shasha O(m²n²) only in adversarial tree shapes, better on average
([tree-edit-distance.dbresearch.uni-salzburg.at](https://tree-edit-distance.dbresearch.uni-salzburg.at/)).
Gives a graded distance, which naturally supports a near-match/family tier via a threshold — but
it assumes sibling order matters, and DOM composite children (nav links, form fields) don't have a
canonical "correct" order for matching purposes; forcing order in means two navbars with the same
links reordered would score as edits rather than a match unless the implementation is adapted to
unordered comparison, which drops the O(n³) bound.

**2. Canonical/Merkle-style structural hashing (AHU algorithm).** Aho, Hopcroft & Ullman's
classical algorithm (surveyed recently in Bosc & Angeles-de-Almeida, *Revisiting Tree Isomorphism:
An Algorithmic Bric-à-Brac*, [arXiv:2309.14441](https://arxiv.org/abs/2309.14441)) computes a
canonical form for a rooted, **unordered**, labeled tree in **linear time**: label every leaf,
then bottom-up compute each node's signature as a sorted tuple of `(node's own label, children's
already-computed signatures)`, so isomorphic subtrees always hash identically regardless of child
order. Two composite subtrees collapse to the same hash iff they are structurally identical up to
the label function chosen — exactly the "canonical/Merkle-style structural hashing that ignores
page-specific leaf values" the ticket names, where the label function is deliberately built from
`tag`/`role`/`component_type`/`input_type` (or a coarsened form of them) rather than `text` or
geometry, so two same-shaped navbars with different link text still hash equal. This gives **exact
match only** (collapse tier) — a single differing descendant changes the hash completely, with no
graded notion of "close."

**3. Frequent subtree mining (TreeMiner, FREQT, SLEUTH).** Finds subtree patterns whose support
(occurrence count) across a tree database exceeds a threshold — TreeMiner (Zaki, 2002) for ordered
embedded subtrees, SLEUTH for unordered embedded subtrees
([Frequent subtree mining](https://en.wikipedia.org/wiki/Frequent_subtree_mining)). This solves a
different problem than the ticket's: it discovers *which* subtree shapes recur across the whole
corpus (unsupervised pattern discovery), not "does *this* composite on page A match *that*
composite on page B." It is also the most machinery-heavy option — general subgraph isomorphism
is NP-complete, and though tree-restricted variants are polynomial, the mining algorithms still
carry real implementation and tuning surface (support thresholds, candidate-generation strategy,
Apriori-style level-wise search) disproportionate to a single-page composite tree.

**4. Tree alignment / bottom-up mapping heuristics** (e.g. the older Selkow/Yang tree-alignment
line, or the many DOM-specific "structural clustering" heuristics used in web wrapper induction).
These trade edit-distance's optimality guarantee for near-linear heuristics tailored to HTML/DOM
shapes specifically. They are the natural fit for "near-match," but the general literature here is
fragmented (no single well-adopted reference implementation the way APTED or AHU are), which cuts
against the "dependency-light and explainable" requirement — adopting one means either vendoring
a bespoke algorithm or depending on a niche library with no ecosystem weight.

## Recommendation

**A two-stage pipeline, composing options 1 and 2 rather than picking one:**

1. **Collapse tier — canonical structural hashing (AHU-style), on top of the leaf-level feature
   vector.** Materialize each `Container` root's subtree via one `CONTAINS*` traversal, replace
   each node's label with a coarsened structural signature derived from the *other* ticket's
   deterministic leaf feature vector (the fields that describe shape/kind, e.g. `tag`,
   `component_type`, `role`, `input_type` — deliberately excluding page-specific values like
   `text`, `href`, geometry), then compute the AHU canonical hash bottom-up. Two composites hash
   identically iff structurally identical under that label function, independent of child order —
   directly answering "collapse this navbar into one canonical node." This is linear-time, needs
   no external library (it is a straightforward bottom-up traversal + tuple-sort, in keeping with
   `component_family.py`'s existing hand-rolled Jaccard/union-find pattern), and is fully
   explainable: a "why did these collapse" answer is just "same signature at every level."

2. **Family tier — bounded tree edit distance (or a distance-in-the-spirit-of-APTED heuristic),
   scoped to same-hash-prefix or same-root-tag candidates only.** Run a graded distance only
   between composites that already share a coarse bucket (same root `tag`/`component_type`, the
   same bucketing discipline `component_family.py` already uses before its Jaccard pass) and
   didn't collapse exactly in stage 1. Because composite trees here are small
   (single-page-subtree scale, not corpus scale), full APTED's O(n³) is affordable at this stage
   even without adopting the library — a plain Zhang-Shasha or even a simpler unordered
   multiset-of-child-signatures Jaccard (reusing stage 1's per-node signatures as the token
   alphabet, echoing `_similarity` in `component_family.py`) is sufficient given the size bound
   the map itself set, and keeps the same "no new dependency" posture as stage 1. Threshold the
   distance/similarity the same way the existing Jaccard floor works (`_SIMILARITY_THRESHOLD` in
   `component_family.py`) to decide "close enough to be a family, not close enough to collapse."

**Why not the other two options as the primary mechanism:** tree edit distance alone (option 1)
either assumes an ordering the domain doesn't have, or drops to unordered edit distance where the
complexity and reference implementations (APTED) don't cover the unordered case cleanly — using it
only as stage 2's *bounded, pre-bucketed* comparison sidesteps that scaling and ordering concern.
Frequent subtree mining (option 3) answers a different question (corpus-wide pattern discovery,
not pairwise/threshold matching) and brings machinery (Apriori-style candidate generation, support
tuning) the ticket's "dependency-light" constraint rules out. Ad hoc tree alignment (option 4) has
no canonical, well-adopted reference to anchor an explainable implementation against, unlike AHU
(a 1970s textbook algorithm, recently re-surveyed and still the reference point for unordered tree
canonicalization) and Zhang-Shasha/APTED (the reference point for tree edit distance).

**What this needs from the rest of the map that isn't decided here:** the label function stage 1
hashes on (which subset/coarsening of the leaf feature vector counts as "structural" vs.
"page-specific") is designed by the sibling leaf-feature-vector ticket, not this one — this survey
only establishes that composing a canonical-hash collapse tier with a bucketed edit-distance/
signature-Jaccard family tier is the shape that fits the schema and the map's constraints, not the
specific label cutoff.

## Sources

- `database/ladybug/schema.py`, `docs/dev/database/ladybug/schema.md` (this repo) — `Container`/
  `Component`/`CONTAINS` shape.
- `generators/component_family.py` (this repo) — existing deterministic Jaccard/union-find pattern
  this recommendation extends rather than replaces wholesale.
- Pawlik, M. & Augsten, N., *Efficient Computation of the Tree Edit Distance*, ACM TODS 40(1), 2015;
  *Tree edit distance: Robust and memory-efficient*, Information Systems 56, 2016;
  [tree-edit-distance.dbresearch.uni-salzburg.at](https://tree-edit-distance.dbresearch.uni-salzburg.at/)
  (APTED/RTED complexity and scope).
- Bosc, G., *Revisiting Tree Isomorphism: An Algorithmic Bric-à-Brac*,
  [arXiv:2309.14441](https://arxiv.org/abs/2309.14441) (AHU canonical-form algorithm).
- [Frequent subtree mining](https://en.wikipedia.org/wiki/Frequent_subtree_mining) — TreeMiner/
  SLEUTH scope and NP-completeness of general subgraph isomorphism.
