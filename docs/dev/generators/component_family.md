# `generators/component_family.py`

## module

Post-hoc, whole-site inference of reusable component "families" (a
Button pattern, a combobox pattern, ...) from components a crawl already
discovered - not part of the live per-page write path `GraphStoreSink`
drives during a crawl (see `core/engine.py::_apply_component_families`
for where this runs: once, after `MechanicalCrawler.crawl_site` finishes,
since clustering needs to see every discovered component across the
whole site at once).

Pure, no I/O, same placement discipline as `component_classifier.py` -
the impure read-from-`GraphStore`/write-back-to-`GraphStore` orchestration
lives in `engine.py`, not here.

### One output: is this the same reusable pattern as that other one?

`build_component_families` groups by `(tag, component_type)`, then by CSS-class
similarity, into a brand-new `ComponentFamily` record pointing at the existing
`Component` rows via their `member_paths`. A cluster needs 2+ members after
similarity clustering to become a family - a component with no siblings isn't
a reusable pattern, it's just a component.

A coarser, purely tag-based grouping (`tags_with_multiple_instances`/
`label_for_tag`) used to live here too, feeding `GraphStore.apply_tag_labels`
so Neo4j Browser could color nodes by tag - removed along with that backend,
since it was purely a Browser-coloring affordance with no equivalent once
nothing renders the graph visually.

### Worked example (real data, empanad.app)

Two real components discovered on the same site:

```python
{"page_url": "empanad.app/o/x", "path": "...button:nth-of-type(1)",
 "tag": "button", "component_type": "button",
 "css_class": "border-2 border-primary disabled:opacity-40 h-8 w-8 rounded-full ..."}
{"page_url": "empanad.app/o/x", "path": "...button:nth-of-type(2)",
 "tag": "button", "component_type": "button",
 "css_class": "border-2 border-primary disabled:opacity-40 h-8 w-8 rounded-full ..."}
```

- **Family clustering**: both share `(tag="button", component_type="button")`
  *and* their `css_class` sets are identical (similarity 1.0, well above the
  0.5 threshold) -> one `ComponentFamily(tag="button", component_type=
  "button", common_classes=(...every shared class...), member_paths=(both
  paths above))` is returned. This specific pair was the site's quantity-
  stepper "+ / -" buttons - two visually-identical, independently-discovered
  DOM elements correctly inferred as one reusable circular-button pattern.

### `component_type` value reference

`component_type` isn't computed by this module - it's whatever
`component_classifier.classify_component_type` already assigned each
component at crawl time (before this module ever sees it). Common values,
for context on what `build_component_families` buckets by: `"button"`,
`"submit button"`, `"link"`, `"checkbox"`, `"radio button"`, `"toggle
switch"`, `"tab"`, `"combobox (searchable dropdown)"`, `"native dropdown
(select)"`, `"list/menu option"`, `"text field (text)"` (or `"(number)"`,
`"(email)"`, etc. per `input_type`), `"custom control (component-library
element, no native tag/role)"`, and the generic fallback `"element"`. See
`component_classifier.md#classify_component_type` for the full, current
rule set - it can gain new values over time; nothing in this module needs
updating when it does, since bucketing is by whatever string that function
returns, not a fixed enum.

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
a reusable pattern, it's just a component.

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
returned `ComponentFamily` (`core/interfaces.py`) is the
intersection of every member's own classes - a human-readable summary
of what the family visually has in common. `member_paths` is sorted
before being returned, so a round-trip through the `GraphStore`
backend (`DuckDBGraphStore.get_component_families` has its own matching
`ORDER BY`) compares equal regardless of clustering/iteration order.
