# `generators/requirements.py`

## module

`requirements.json` + `prd.md`, per docs/adr/0009 - EARS-syntax
requirements extracted from the crawl graph, replacing the retired
LLM-narrated "Digital Blueprint" (`graph_prd_synthesizer.py`) entirely.
Fully deterministic, no model call anywhere.

**What each EARS pattern is derived from, and what stays reserved.**
`event_driven` and `ubiquitous` come from `InferredRequest.triggered_by`/
`.loaded_by` - real observed network traffic (`confidence: "observed"`).
`unwanted_behavior` comes from an observed failure status code - also
`"observed"`. `optional_feature` comes from `data-model.json`'s own
`nullable` fields - a declared-markup heuristic, so `"inferred"`, not
`"observed"`. `state_driven` stays unused: pragma has no state-detection
instrumentation, so nothing here can back a WHILE-clause honestly.
`confidence: "assumed"` is never emitted either - pragma has no
extraction rule based on convention rather than observation.

Retiring `graph_prd_synthesizer.py` also retired `prd_synth_batch_size`
(`core/config.py`/`core/engine.py`/`core/docs_engine.py`) - a
per-run-config knob for an LLM batch-summarize call that no longer
exists, removed rather than left as dead configuration.

## _requirement_id

`REQ-<hash>` (ADR-0009 point 1, ADR-0015's `sha1(...)[:10]` algorithm) -
deterministic across runs regardless of discovery order, unlike a
sequential counter. `ears_pattern + trigger + target` is the identity-
defining input, per the ADR's own formula.

## _RequirementFacts

What one extraction rule knows about one requirement, before
`_requirement` turns it into `requirements.json`'s own shape - kept as
one object rather than threaded through as individual arguments, the
"more than three arguments becomes a dataclass" rule every other
multi-fact assembly in this codebase follows.

## _event_driven_requirements

WHEN a component is interacted with, THE SYSTEM SHALL call the endpoint
it triggered - one requirement per distinct `(page, path)` trigger in
`InferredRequest.triggered_by`.

## _ubiquitous_requirements

THE SYSTEM SHALL retrieve data automatically when a screen is displayed -
one requirement per page in `InferredRequest.loaded_by`, the calls a
page's own load fires with no component involved.

## _unwanted_behavior_requirements

IF a call fails, THEN THE SYSTEM SHALL answer with the observed failure
status - the crawl only ever captures the response's own status code,
never the resulting UI, hence the `open_questions` entry every one of
these carries.

## _optional_feature_requirements

WHERE a declared-optional field is provided, THE SYSTEM SHALL accept it
- `nullable` fields only, from `data-model.json`'s own entities
(`generators/data_model.py::build_data_model_document`, imported
directly rather than re-derived).

## build_requirements_document

Assembles every EARS pattern this crawl has real support for,
deduplicated by `id` - the same deterministic hash collapses a genuinely
repeated observation (two components triggering the identical call, or
two runs) into one requirement rather than one per occurrence.

## _screen_graph

A minimal `Pantalla`-only `@graph`-shaped list - just enough for
`core/graph_metrics.py`'s module derivation. Built directly here rather
than through `generators/graph_export.py::build_export_graph` to avoid a
circular import: `graph_export.py` itself imports this module's
`build_requirements_document`, for `Requisito` population (ADR-0009
point 5). Page-to-page `navega_a` only (no component-attributed edges) -
module derivation only looks at `Pantalla` nodes regardless of which
edges reach them, so the full richness `graph_export.py` builds isn't
needed for this narrower purpose.

## _screen_module_labels

`{SCR-<hash>: module_label}` for every screen with a derived module -
`prd.md`'s own grouping (ADR-0009 point 4), computed the same hybrid
path-prefix/Leiden pass `architecture.calm.json` uses (docs/adr/0007),
not a second, differently-derived module structure. Module assignment
itself isn't part of `requirements.json`'s own schema - ADR-0009 names
module grouping as `prd.md`'s concern, not the source document's, so
this is view-only and never touches `build_requirements_document`.

## _render_prd_view

`prd.md` - mechanically rendered from `requirements.json`, grouped by
architectural module (ADR-0007) and HITL review status (ADR-0009 point
4), never hand-authored in parallel with it. A requirement citing no
screen (an `unwanted_behavior`/`optional_feature` requirement, which
never link a `screens` entry) lands in its own "Not tied to a screen"
section rather than being silently dropped.

## RequirementsDocument

`requirements.json` (source, schema-validated) and `prd.md` (view) -
registered as `"prd"`, the same name `graph_prd_synthesizer.py`'s own
`GraphPRDSynthesizer` used, so no config or run history has to change to
keep working.
