# `generators/confidence_summary.py`

## module

`confidence-summary.json` - derived confidence rollups across four
source documents, citing each by reference, docs/adr/0029.

**Why the three shapes.** Only `prd` calls its own field `confidence`
literally (`observed`/`inferred`/`assumed`, ADR-0009) - rolled up by
count per category. `data-model.json`'s own `confidence` is a numeric
0-1 score (ADR-0008), rolled up as count/mean/min/max rather than
forced into `prd`'s three categories, which were never built to
describe a continuous score. `usability`/`accessibility` carry no field
literally named `confidence` at all; their EARL `level` (ADR-0011/0012)
is the one dimension that varies per finding and speaks to how much
scrutiny it deserves - rolled up by count per level, the same shape
`prd`'s own rollup uses.

## _prd_rollup

Calls `requirements.build_requirements_document` directly - never a
second, independently-derived confidence tally.

## _data_model_rollup

`None` for every statistic when no field exists to average - never a
fabricated `0`.

## _level_rollup

Shared by both `usability` and `accessibility` - identical EARL
`level` shape, one function rather than two near-duplicates.

## build_confidence_summary

Every rollup calls its source's own real build function directly - the
"call the real build function, never read a file" discipline every
cross-generator call in this map already follows.

## _render_confidence_summary_view

Mechanically rendered from `confidence-summary.json`'s own rollups -
never hand-authored in parallel with it.

## ConfidenceSummaryDocument

Source (`confidence-summary.json`, schema-validated) + view
(`confidence-summary.md`) split. `dashboard`'s own landing-page tile
(ADR-0016, amended) reads `sources.prd` directly from this file instead
of recomputing the same rollup inline from `requirements.json`.
