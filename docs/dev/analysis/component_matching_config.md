# analysis/component_matching_config.py

## module

Tunables for the component-matching pipeline (issue #127) - the leaf
feature-vector block weights `leaf_feature_vector.py` applies and the
leaf/composite thresholds and bucketing slack #132/#133 decided, all in one
place per `docs/dev/generators/matching-threshold-calibration.md`.

Deliberately its own file, `config/component_matching.yaml`, not a block
inside `pragma.yaml` - this map's tunables are a distinct concern from the
general run config.

The merge discipline mirrors `core/config.py::PragmaConfig._apply_yaml` - a
missing file, or a missing/unknown key within it, never raises; it falls
back to the hardcoded default.

## LeafWeights

Per-block scale applied to a leaf feature vector's slices before
concatenation - the knob that controls how much each block influences the
resulting cosine similarity.

## MatchingThresholds

Where "family" ends and "exact reuse" begins, at both the leaf and
composite tiers - issue #133's four independent constants.

## CompositeBucketing

How much two composites' child counts may differ by and still be compared -
issue #132 step 1's bucketing slack, before any per-child work runs.

## ComponentMatchingConfig

The whole matching pipeline's tunables, loaded once per run and passed into
whichever stage needs them.

## load

Reads `path`, falling back to every hardcoded default for a missing file, a
missing block, or a missing/unknown key within one.

## _merge_block

One nested block (`LeafWeights`, `MatchingThresholds`, `CompositeBucketing`)
built from its own defaults, overridden field-by-field by whichever keys a
YAML block actually has - an absent block, an absent key, or a key the
dataclass doesn't define are all silently ignored rather than raising.
