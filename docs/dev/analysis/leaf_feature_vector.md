# analysis/leaf_feature_vector.py

## module

Leaf-level component feature vector - issue #131's design
(`docs/dev/generators/leaf-feature-vector-design.md`), implemented as a pure
value-producing function. Replaces `generators/component_family.py`'s
Jaccard-on-`css_class` clustering as the similarity signal two `Component`
records are compared by; storage into a real Kùzu `FLOAT[169]` column and
wiring into the matching pipeline is issue #139's job, not this module's -
no I/O here, no Kùzu.

`leaf_feature_vector` takes one component record - a plain dict shaped like
`DESCRIPTIVE_COMPONENT_FIELDS`/`ComponentFacts` (the same flat shape
`database/ladybug/component.py::get_component_ledger` already returns per
component) - plus that page/site's `GeometryBuckets`, and returns one
169-dim `list[float]`.

## _bucket

`hashlib.sha1`, never Python's built-in `hash()` - process-randomized by
`PYTHONHASHSEED`, not reproducible across runs.

## _hash_one_hot

One field's value, hashed into one of `bucket_count` slots. An empty string
hashes like any other value, so "this component has no role" collides into
one shared bucket rather than being dropped - lacking an attribute is itself
a signal.

## _hash_multi_hot

`css_class`'s encoding - one hash per whitespace-split token, OR'd into a
binary vector, so a component's *set* of classes (independent of order)
determines this slice.

## _closed_one_hot

One-hot over a small, known, closed value set (`COMPONENT_TYPE_VALUES`,
`POSITION_VALUES`) rather than a hash bucket - no collision risk, since the
whole vocabulary is enumerated.

## COMPONENT_TYPE_VALUES

The full closed set `generators/component_classifier.py::
classify_component_type` can return - 13 values, its templated `"text field
(<input_type>)"` branch collapsed to the fixed `"text field"` (the specific
`input_type` is already its own hashed field). Single source of truth for
this vocabulary; listed explicitly here rather than derived at runtime so
the vector's dimensionality never shifts silently if that function grows a
branch.

## _collapsed_component_type

Maps any `"text field (...)"` value to the fixed `"text field"`.

## _parse_font_size

`"16px"` -> `16.0`; anything unparseable -> `0.0`, the same "absence is a
shared trait" default the hash blocks use.

## _parse_font_weight

Computed-style `font-weight` is already numeric (`getComputedStyle`
resolves `normal`/`bold` to a number) - parsed directly, `0.0` on failure.

## _color_channels

A parsed CSS color (`generators/color_space.py::parse_css_color`) as an
`(r, g, b)` triplet, each channel `/255`. `(0.0, 0.0, 0.0)` for an
unparseable or fully transparent color.

## GeometryBuckets

Tertile edges for `width`/`height`, one pair per `(tag, component_type)`
group.

## compute_geometry_buckets

One tertile-edge pair per `(tag, component_type)` group, for both `width`
and `height` - grouped so a component's size reads as small/medium/large
relative to its own kind on this site, not against every component
regardless of what it is. The one part of this design that needs the full
component set in hand before any single vector can be computed. A group
with fewer than 3 members gets no edges; `_geometry_bucket_index` falls back
to the middle bucket for any component whose group has none.

## leaf_feature_vector

The 169-dim feature vector for one component record - concatenated blocks,
each scaled by its `ComponentMatchingConfig.leaf_weights` entry before
joining, so weight directly controls that block's share of the final cosine
similarity. `x`/`y`/`element_id` are excluded (page-position and
DOM-remount-unstable, not identity); `text`/`label` are excluded too (kept
for a separate, cheaper text-proximity refinement pass, #128).
