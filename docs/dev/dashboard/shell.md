# `dashboard/shell.py`

## module

The Phase C dashboard shell (ADR-0016 point 4), ticket #125 - the
landing page every other dashboard page is reached from, plus one
per-document render and one per-concern detail page. "Variant C" from
the validated prototype (`prototype/dashboard-80`) - no persistent
sidebar or top bar, the landing page carries the navigation.

**Why KPI numbers come from two different places.** Pages/components
counts come from the caller's own already-computed `KpiContext` -
`core/docs_engine.py`/`core/engine.py` both already compute
`finished_pages`/`total_pages`/`unexplored_components`/`total_components`
locally for `record_run_manifest`; `coverage.json`'s own serialized
JSON shape doesn't expose `components_explored` at all (only
`interactions.detected`, a different number - total known components,
not "how many were interacted with"), so there's no file to read this
pair from anyway. Endpoints and requirement confidence, by contrast, do
have a real dedicated source document each (`coverage.json`,
`confidence-summary.json`) - read from there, never recomputed.

## KpiContext

The two counts `coverage.json` can't supply, passed through from the
caller rather than re-derived.

## DashboardRunContext

`write_dashboard`'s own bundle - `kpi_context` plus `site`/`out_dir`,
kept out of `KpiContext` itself since those two are about identity and
location, not metrics.

## _source_json

`None` (not an exception, not a fabricated empty dict) when a config
turned a source document off this run - a dashboard KPI reads the same
"maybe absent" signal `manifest.json`'s own `status: "off"` already
encodes.

## _kpi_section

The crawl-wide metrics row (ADR-0016 point 4): pages/components from
the caller's own counts, endpoints from `coverage.json`, requirement
confidence from `confidence-summary.json`.

## _document_slug

`filename` alone collides for a source/view pair sharing one stem
(`coverage`/`coverage`) - pairing it with `kind` resolves that, the
same fact `master_document.py`'s own format lookup already had to
guard against (ticket #109).

## build_dashboard

Pure - takes every document's content already read, returns
`{relative_path: html}` for the caller to write. `master`'s own three
outputs (`master.md`/`llms.txt`/`manifest.json`) are excluded from both
the concern grid and the per-document renders - they describe the run
as a whole, not one concern, and are already reachable through the raw
files directly.

## write_dashboard

The one impure entry point - reads every produced document's content
back off disk (the only content `run_document_pipeline`'s own return
value doesn't carry, only paths and metadata), then writes
`build_dashboard`'s result.
