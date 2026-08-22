# Audit: downstream consumers of `css_class` / leaf-vector shape (#166)

Wayfinder ticket #166, child of map #164. Question: what in this codebase currently reads or
depends on `Component.css_class`'s raw string shape, or on `analysis/leaf_feature_vector.py`'s
vector composition (block order, dimensionality, weights) — and would replacing the `css_class`
block with semantic/conceptual features break any of it?

All line numbers verified directly against the source on this branch (`research/css-class-leaf-
vector-audit`, cut from `dev` at `c5fb0d3`), not against map #164's summary.

## Vector composition, verified directly

`analysis/leaf_feature_vector.py::leaf_feature_vector` concatenates five weighted blocks, in this
order: `structural`, `identity_strings`, `css_class_tokens`, `style`, `geometry` (lines 278–284).
`css_class` is block 3 of 5.

Actual per-block dimensionality, confirmed by running the function (`python3 -c "...
len(leaf_feature_vector({}, gb))"` → `169`) and by reading the block builders:

- `structural` = 60 (`tag` 16 + `role` 16 + `input_type` 12 + `component_type` closed-vocab 13 +
  3 bools)
- `identity_strings` = 48 (`href`/`name`/`form`, 16 each)
- `css_class` = 32 (`_CSS_CLASS_BUCKETS`, line 104)
- `style` = 23 (6 color channels + 2 scaled numerics + `display` 10 + `position` closed-vocab 5)
- `geometry` = 6 (3 + 3, width/height tertile one-hots)
- **Total = 169**, not the "168" the module's own docstring claims (line 15: `"168"-dim`) and
  that map #164's notes echo. This is a pre-existing doc/code drift, independent of #166's
  question — worth a one-line docstring fix whenever `analysis/leaf_feature_vector.py` is next
  touched, but out of scope here.

`css_class` encoding, confirmed at lines 233/260: `component.get("css_class", "")` is
whitespace-split (`.split()`) and each token hashed into one of 32 buckets via `_hash_multi_hot`
(sha1-based, line 41–43), OR'd into a binary vector — i.e. exactly the raw-string/bag-of-tokens
shape #164 described. Weight is `0.6` (`analysis/component_matching_config.py:40`,
`LeafWeights.css_class`), confirmed directly, not inferred.

`analysis/component_matching_config.py` never references vector dimensionality or block order —
it only carries the five `LeafWeights` floats, threshold floats, and bucketing slack. No coupling
to composition beyond the weight names themselves.

## What breaks

**1. `analysis/composite_matching.py` — `container_root_vector` (lines 73–90).** This is the
single most important finding: composite/subtree matching builds its own, second, independent
css_class-block encoding for `Container` roots, reusing the *private* helpers
`_hash_multi_hot`/`_hash_one_hot` imported directly from `leaf_feature_vector.py` (line 29) and
`weights.css_class` from the same `LeafWeights` (line 89–90). It hashes `container.css_class`
(the `Container` node's own raw class string, not a `Component`'s) into its own 32-bucket block
(`_ROOT_CSS_CLASS_BUCKETS`, line 35) and scales it by the same `0.6` weight the leaf vector uses.
Replacing "the `css_class` block" in `leaf_feature_vector.py` alone, without also touching this
file, leaves a second raw-css_class-hashing code path live and unconverted — `composite_score`
would keep clustering composite roots partly by raw class tokens even after leaf components
stopped doing so. If the leaf-vector change also removes or renames `_hash_multi_hot`, this file
fails to import at all (line 29).
  - `tests/test_composite_matching.py::test_container_root_vector_reflects_landmark_and_css_class`
    (line 119) asserts directly on this: two containers differing only by `css_class` must
    produce different vectors. Needs updating (or replacing) alongside any change here.

**2. `generators/component_catalog.py` — `_extra_classes`/`_variants` (lines 134–136, 176–189).**
Independent of the vector entirely: `_extra_classes` does `set(css_class.split()) - set(common)`
directly on `member.get("css_class")`, and `_variants` groups catalog members into
`CatalogVariant`s keyed on that leftover token set plus `background_color`. This is a second,
separate raw-string dependency on `css_class`'s whitespace-token shape — it reads the field
straight from the component dict, not through `leaf_feature_vector`'s output. If `css_class` were
dropped or reshaped (not just re-weighted in the vector) as part of the semantic-features swap,
this breaks the "primary/secondary button = two variants of one component" behavior entirely.
  - `tests/test_component_catalog.py::test_members_differing_only_by_a_modifier_class_are_variants_not_components`
    (line 153) asserts `modifiers == {("btn-primary",), ("btn-danger",)}` directly off hand-built
    `css_class` strings — would fail if the raw-string shape changed.

**3. `generators/custom_elements.py` (lines 44–45, 196–202) — transitively via `component_catalog`'s
variants.** `_variant_attributes` (or equivalent, line 44) does
`attributes["class"] = " ".join(variant.modifiers)`, and the CEM markdown table renders
`v['attributes'].get('class', ...)`. This is a second-order consumer: it doesn't touch
`css_class` directly, but it consumes `CatalogVariant.modifiers`, which is only meaningful because
of (2) above.
  - `tests/test_custom_elements.py::test_variants_become_x_observed_variants_with_deterministic_screen_ids`
    (line 82) asserts `{v["attributes"]["class"] for v in variants} == {"btn-primary",
    "btn-danger"}` — same fragility as (2)'s test, one hop downstream.

**4. `analysis/component_matching_pipeline.py::_common_classes` (lines 163–168).** A *third*
independent raw-css_class-token consumer: `frozenset((m.get("css_class") or "").split())`,
intersected across a leaf family's members to populate `ComponentFamily.common_classes`
(`core/data_contracts.py:160`). This is Jaccard-style raw-token logic living inside the pipeline
that also does vector-based clustering — the two are not the same code path. Note
`core/data_contracts.py`'s own docstring (lines 109–116) says this dataclass's *shape* already
"retired the earlier CSS-class-Jaccard version" as the clustering signal, but `common_classes` as
a *reported field* on the resulting family is still computed by raw-token intersection today, not
derived from the vector. Replacing the vector's `css_class` block does not by itself change this
field's behavior, but if the semantic-features work also intends to stop treating `css_class` as
meaningful raw text, this function needs a decision too (out of scope for #166, flagged for
#168).
  - No dedicated test file exists for `_common_classes` (there is no
    `tests/test_component_matching_pipeline.py`; the ticket's premise of a
    `tests/test_component_family.py` no longer holds — see "note on file naming" below).

**5. `generators/component_family_narrator.py::family_signature` (line 56).** Includes
`tuple(family.common_classes)` in the cache key used to carry a family's narrated `purpose`
across re-clustering runs. Not a hard break (it degrades gracefully — a changed signature just
means the purpose gets re-narrated instead of reused), but worth naming: if `common_classes`'
raw-token semantics change, previously-narrated purposes silently stop being recognized as "the
same family" even when nothing user-visible changed. No test currently pins the *value* of a
signature tuple's `common_classes` slot specifically, so nothing fails outright, but behavior
(narration cache hit rate) would shift.

**6. `tests/test_leaf_feature_vector.py` — direct, block-level tests.** These are exactly what
would need rewriting for the semantic/conceptual-features implementation ticket itself, not
incidental breakage:
  - `test_vector_length_matches_the_documented_dimensionality` (line 28): `assert len(vector) ==
    169` — hardcoded total dimensionality. Any change to the css_class block's bucket count (or
    replacement with a differently-sized semantic block) changes this number.
  - `test_missing_facts_fields_default_without_raising` (line 85) and
    `test_a_component_type_with_no_geometry_siblings_falls_back_to_the_middle_bucket` (line 105):
    same `== 169` assertion, two more places.
  - `test_css_class_overlap_increases_similarity_over_no_overlap` (line 74): asserts cosine
    similarity is higher for two components sharing class tokens than for two that don't — this
    is testing the *token-hash* mechanism specifically, not just "css_class contributes to
    similarity somehow." A semantic/conceptual replacement could preserve the *outcome* (shared
    semantic features → higher similarity) while this test's mechanism-specific framing would
    still need rewriting to match the new encoding.
  - `test_leaf_weights_scale_a_block_s_contribution` (line 116): imports `_CSS_CLASS_BUCKETS` and
    `_hash_multi_hot` directly from `leaf_feature_vector.py` and recomputes the raw block to
    assert the weight scales it exactly. Directly coupled to both the private helper name and the
    hash-based encoding; would need a full rewrite, not just a number update.

## What's fine

- **`analysis/component_matching_config.py`** — no coupling beyond the `css_class` weight field
  name (`LeafWeights.css_class`); doesn't know or assume anything about dimensionality, block
  order, or hashing. Renaming/repurposing this one field is a mechanical, low-risk change.
- **`generators/graph_export.py`** — grepped for `css_class`, `vector`, `leaf_feature`, `168`,
  `169`: zero matches. The exported graph JSON does not surface `css_class` as a raw field or any
  vector internals.
- **`generators/component_family_narrator.py`** — beyond the `family_signature` caching nuance
  above (item 5), the LLM prompt itself (`PURPOSE_SYSTEM_INSTRUCTION`, lines 22–29) explicitly
  tells the model to describe functional purpose "never its visual appearance (color, size, CSS
  classes)" — narration was already designed not to depend on `css_class` content.
- **Database/storage layer** (`database/ladybug/schema.py`, `containment.py`,
  `container_forest.py`, `spiders/orchestration/graph_sink/component_facts.py`) — these persist
  `css_class` as a plain `STRING` column on `Component`/`Container` and pass it through verbatim.
  They have no opinion on the vector or on the raw string's internal token shape; unaffected
  either way unless the field itself is removed from the schema (a separate, bigger decision than
  #166 covers).
- **Fixture-only test files** — `tests/test_content_inventory.py`, `tests/test_ladybug_containment.py`,
  `tests/test_graph_sink_component_facts.py`, `tests/test_cluster_engine.py`,
  `tests/test_ladybug_observation.py`, `tests/test_accessibility.py` all pass a `css_class` string
  through as an ordinary fixture field (persistence round-trip, `ComponentFacts` construction,
  accessibility-rule distinctness) without asserting anything about its internal token structure.
  These would keep passing unchanged regardless of what replaces the vector's css_class block.

## What needs updating as part of #168 (implementation ticket, out of scope here)

- `analysis/leaf_feature_vector.py`'s css_class block itself (the actual swap).
- `analysis/composite_matching.py::container_root_vector` — the second, independent hashing path
  for `Container.css_class` (item 1) must be converted in lockstep, or explicitly deferred with a
  stated reason; leaving it hash-based while the leaf vector goes semantic is an inconsistency,
  not a neutral choice.
- `tests/test_leaf_feature_vector.py`'s dimensionality (`169` in three places) and its two
  css_class-mechanism-specific tests (items 6).
- `tests/test_composite_matching.py::test_container_root_vector_reflects_landmark_and_css_class`
  once (1) is converted.
- The module docstring's stale `"168"`-dim claim (line 15) — trivial, but should be corrected
  alongside whatever change touches this file next, whether or not it's #168.

## What can safely be deferred (not required by #166 or necessarily by #168)

- `generators/component_catalog.py`'s `_extra_classes`/`_variants` (item 2) and
  `generators/custom_elements.py`'s consumption of `modifiers` (item 3): these read
  `Component.css_class` as raw text directly, entirely outside the vector/matching pipeline.
  They only break if the *field* `css_class` itself is removed or reshaped — not if only its
  *vector encoding* changes. If #168's scope is "replace the vector block," these two are
  unaffected and can be left alone; if #168's scope grows to "stop treating raw `css_class` as
  meaningful anywhere," these become in-scope and should be called out explicitly then.
- `analysis/component_matching_pipeline.py::_common_classes` (item 4) and
  `ComponentFamily.common_classes` — same reasoning: raw-token intersection reporting, decoupled
  from the vector, only affected if `css_class` the field (not the block) changes shape.
- `generators/component_family_narrator.py::family_signature`'s narration-cache-key nuance
  (item 5): a soft degradation (re-narration, not breakage), fine to leave unaddressed unless
  narration cost becomes a concern.

## Note on file naming vs. the audit's original assumptions

Two files this audit's own instructions named as "at minimum, read" turned out not to exist on
`dev`: `tests/test_component_family.py` (there is no `generators/component_family.py` either —
its Jaccard-clustering role was superseded by `analysis/component_matching_pipeline.py` +
`analysis/leaf_feature_vector.py` per issue #139, confirmed by
`core/data_contracts.py`'s own `ComponentFamily` docstring, lines 112–116: "retired the earlier
CSS-class-Jaccard version this dataclass's shape predates"). The actual test coverage for the
current pipeline's family-building lives spread across `tests/test_leaf_feature_vector.py`,
`tests/test_composite_matching.py`, and `tests/test_component_matching_config.py`; there is no
dedicated `tests/test_component_matching_pipeline.py` covering `_build_leaf_families` or
`_common_classes` directly today.

## #159 question: has any Graph-card code landed that reads `css_class` or vector shape?

**No.** Verified independently, not from the issue's own claims:

- `git log --all --oneline -- dashboard/` shows only pre-existing Dashboard Phase A–C commits
  (`8531ee1`, `a42f6a8`, `dadcdfe`, `f38de97`, `34ff300`, `defdc41`, `b01cda9`) — none reference
  #159–#163, none postdate the graph-viz-library research.
- `git log --all --oneline --grep="#159"` / `--grep="#160"` / `--grep="#161"` / `--grep="#162"` /
  `--grep="#163"` all return zero commits.
- `grep -rn "css_class\|leaf_feature_vector\|component_matching" dashboard/` returns zero matches
  — current `dashboard/` source (`document_context.py`, `generic_template.py`,
  `redoc_renderer.py`, `renderer_audit.py`, `shell.py`) has no reference to either.
- `gh issue view` confirms current state directly: #160 (graph-viz library pick) is **CLOSED**
  but its own body/comments point to `research/graph-viz-library.md` — a research artifact, no
  code. #161 (flip `export_json` default), #162 (design the Graph card), and #163 (build/wire
  Cytoscape.js) are all **OPEN**, unimplemented.
