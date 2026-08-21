# Calibrating exact-reuse vs family thresholds

Resolves [Calibrate exact-reuse vs family thresholds](https://github.com/ezequielrickert/pragma/issues/133),
child of [Component matching: embedding-based dedup and family grouping](https://github.com/ezequielrickert/pragma/issues/127).

## Four independent thresholds, not two

Leaf-vector cosine similarity ([#131](https://github.com/ezequielrickert/pragma/issues/131),
`docs/dev/generators/leaf-feature-vector-design.md`) and composite coverage-weighted score
([#132](https://github.com/ezequielrickert/pragma/issues/132),
`docs/dev/generators/composite-subtree-matching-design.md`) are different formulas at different
scales — nothing guarantees a leaf-tier cutoff and a composite-tier cutoff land on the same
number. Four named constants, tuned independently:

| Constant | Meaning | Starting value |
|---|---|---|
| `leaf_family` | leaf cosine similarity ≥ this → same family | 0.55 |
| `leaf_exact` | leaf cosine similarity ≥ this → exact-reuse candidate | 0.92 |
| `composite_family` | composite score ≥ this → same family | 0.5 |
| `composite_exact` | composite score ≥ this **and** full child coverage (per #132's hard gate) → collapse | 0.9 |

`leaf_family`'s 0.55 starting point deliberately sits just above `component_family.py`'s current
`_SIMILARITY_THRESHOLD = 0.5` (Jaccard-on-`css_class` only) — the new vector draws on far more
fields, so a slightly higher bar is the reasonable prior before any real tuning happens. The
`exact` values start high on purpose: collapsing merges nodes, an operation that loses
information and is expensive to walk back once other data references the canonical node, unlike
a family grouping, which is cheap to get wrong and easy to revise. Bias toward staying at family
tier when uncertain.

## Where these live: a dedicated config file, not `pragma.yaml`

`pragma.yaml`'s established pattern (`agents.local.*`, per
[#128](https://github.com/ezequielrickert/pragma/issues/128)'s findings) is a free-form nested
dict passed as `**kwargs` into the consuming class's constructor, which defines its own
hardcoded/env-var fallback defaults. This effort follows the same *shape* but a separate *file*
— `config/component_matching.yaml` — holding every tunable number this whole map introduces, not
just this ticket's four thresholds:

```yaml
# config/component_matching.yaml
leaf_weights:
  structural: 1.0
  identity_strings: 0.8
  css_class: 0.6
  style: 0.5
  geometry: 0.15
thresholds:
  leaf_family: 0.55
  leaf_exact: 0.92
  composite_family: 0.5
  composite_exact: 0.9
composite_bucketing:
  child_count_slack: 0.5   # from #132 step 1
```

A loader mirroring `core/config.py`'s existing YAML-merge behavior (missing file or missing key
→ the hardcoded defaults above, never an error) reads this once per run and passes the resulting
values into the matching pipeline's constructor — consistent with the codebase's existing
config-loading discipline, but kept out of `pragma.yaml` itself per your preference, so the whole
matching pipeline's tunables live in one dedicated place instead of mixed into the general
run config.

## Validation: real crawl data exists, use it

`data/sites/austral.edu.ar.lbdb` — 88 pages, 19,804 components, never yet run through the
existing clustering — is sitting in the repo already. Calibration is an empirical pass against
this real dataset (compute leaf/composite scores across its actual component population, inspect
the distribution and a sample of matches/non-matches at the starting thresholds above, adjust),
not something folded into the unit-test suite. `tests/test_component_family.py`'s existing
convention (small hand-authored inline dicts) stays the right shape for *unit* tests — asserting
specific known pairs match or don't at fixed thresholds — but that's a correctness check on the
mechanism, not what calibrates the actual cutoff values. Calibration itself is a manual/analysis
step run against `austral.edu.ar.lbdb`, not automated CI.

## Text-proximity gates the boundary, doesn't score generally

Per [#131](https://github.com/ezequielrickert/pragma/issues/131)'s decision to keep text
similarity out of the indexed vector: the text-proximity refinement pass only runs for pairs
whose leaf/composite score already lands between that tier's `family` and `exact` constants —
the ambiguous zone. A close text match there confirms promotion to `exact`; a distant one leaves
the pair at `family`. Pairs already decisively above or below a threshold never trigger a
text-proximity call at all, keeping the (comparatively expensive, network-calling) text check
off the common path.

## Global defaults, per-site override only if needed

Thresholds start as global defaults — structural/style similarity doesn't mean something
different on one site vs. another the way, say, a content threshold might. `config/
component_matching.yaml` can later grow a per-site override block if a specific site's real
data (once more sites accumulate `.lbdb` files) proves the global defaults wrong for it, but that
override path isn't built until real evidence demands it.
