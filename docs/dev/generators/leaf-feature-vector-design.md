# Leaf-level component feature vector

Resolves [Design leaf-level deterministic feature-vector calculation](https://github.com/ezequielrickert/pragma/issues/131),
child of [Component matching: embedding-based dedup and family grouping](https://github.com/ezequielrickert/pragma/issues/127).

Replaces `generators/component_family.py`'s Jaccard-on-`css_class` clustering. Produces one
fixed-length `float` vector per `Component` node, stored as a Kùzu `FLOAT[169]` column, compared
with **cosine similarity** through `QUERY_VECTOR_INDEX` (per
[#130](https://github.com/ezequielrickert/pragma/issues/130)'s confirmed API).

## Why hashing, not exact vocabulary indexing

Two options were on the table: build an exact per-run vocabulary of every observed `tag`/`role`/
`css_class` value in a first pass, or hash every value into a fixed number of buckets. Hashing
was chosen: it keeps the vector's dimensionality a global constant across every crawled site,
rather than something that has to be recomputed and re-declared per run's schema. The cost is
hash collisions, which shrink as bucket count grows relative to a component's typical value
count — an acceptable trade at the bucket counts below.

All hashing uses `hashlib.sha1(value.encode()).digest()`, never Python's built-in `hash()`
(process-randomized by `PYTHONHASHSEED`, not reproducible across runs).

```python
def _bucket(value: str, bucket_count: int) -> int:
    digest = hashlib.sha1(value.encode()).digest()
    return int.from_bytes(digest[:4], "big") % bucket_count
```

An empty string (a field the component doesn't carry, e.g. no `role`) hashes like any other
value — all "missing this field" instances collide into the same bucket, which is the correct
signal: lacking an attribute is itself a shared trait, not noise to discard.

## Vector layout (169 dims total)

Each block below is a slice of the final vector, scaled by its weight *before* concatenation, so
weight directly controls that block's influence on the final cosine similarity.

| Block | Fields | Encoding | Dims | Weight |
|---|---|---|---|---|
| Structural | `tag`, `role`, `input_type` | single-value hash, one-hot within block's own bucket space (16/16/12) | 44 | 1.0 |
| Structural | `component_type` | one-hot, 13 closed values (see below) | 13 | 1.0 |
| Structural | `disabled`, `required`, `has_form` (derived: `form != ""`) | boolean 0/1 | 3 | 1.0 |
| Identity strings | `href`, `name`, `form` | single-value hash, one-hot, 16 buckets each | 48 | 0.8 |
| Class tokens | `css_class` | multi-value hash, binary multi-hot, 32 buckets (one hash per whitespace-split token, OR'd) | 32 | 0.6 |
| Style — color | `color`, `background_color` | parsed CSS color → RGB triplet, each channel `/255` | 6 | 0.5 |
| Style — scalar | `font_size` (px → `/32`), `font_weight` (→ `/900`) | normalized float | 2 | 0.5 |
| Style — keyword | `display` | single-value hash, one-hot, 10 buckets (open vocabulary) | 10 | 0.5 |
| Style — keyword | `position` | one-hot, 5 closed values (`static`/`relative`/`absolute`/`fixed`/`sticky`) | 5 | 0.5 |
| Geometry | `width`, `height` | per-run tertile bucket within `(tag, component_type)`, one-hot, 3 buckets each | 6 | 0.15 |

`x`/`y` and `element_id` are excluded entirely — `x`/`y` are page-position-dependent, not a
sameness signal; `element_id` is already treated as unreliable elsewhere in this codebase
(`component_matching.py::component_identity()` excludes it for the same reason: ids get
reassigned across a DOM remount).

`component_type`'s 13 closed values: the literal strings `classify_component_type()`
(`generators/component_classifier.py`) can return - 12 of them, plus its templated
`"text field (<input_type>)"` branch collapsed to one generic `"text field"` value for vector
purposes (the specific `input_type` is already captured by its own hashed field above). Corrected
from this doc's original count of 11 while implementing #137 - `analysis/leaf_feature_vector.py::
COMPONENT_TYPE_VALUES` is the enumeration to trust; this is a miscount fix, not a design change.

## Geometry's quantile buckets

Computed in a first pass over the run's `Component` rows, grouped by `(tag, component_type)`:
split each group's `width` values into tertiles (and separately for `height`), then assign each
component to bucket 0/1/2 (small/medium/large *relative to its own kind on this site*). This is
the one part of the design that needs the full component set in hand before any vector is
computed — already true of this pipeline, which runs as a batch pass after static discovery.
This bucketing is also the seed for a later size-variant tag (`sm`/`md`/`lg`) on top of a
recognized family, noted in the map's Not yet specified.

## Text (`text`, `label`) — deliberately excluded from this vector

Per the map's founding decision (text weighted low, kept as signal) and
[#128](https://github.com/ezequielrickert/pragma/issues/128)'s findings (no cheap per-pair
text-similarity path exists yet; needs a new local embeddings-endpoint client), text-proximity
stays **out of this indexed vector** entirely. It's applied as a separate, cheap refinement pass
only to candidate pairs the structural+style vector already places near a threshold — keeping
this vector's dimensionality independent of whatever embedding model that later client calls.
`text` and `label` are concatenated as one string when that refinement pass runs.

## Threshold composition (handed to #133)

This vector and cosine similarity produce one scalar per pair. Where "family" ends and "exact
reuse" begins, and how the separate text-proximity refinement folds into that scalar, is
[Calibrate exact-reuse vs family thresholds](https://github.com/ezequielrickert/pragma/issues/133)'s
job, not this ticket's. The weights above are a starting point (block-level constants, not load-
bearing architecture) meant to be tuned empirically once a real crawl is available to test
against.
