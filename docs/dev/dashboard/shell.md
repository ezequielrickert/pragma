# `dashboard/shell.py`

## module

The Phase C dashboard shell (ADR-0016 point 4), ticket #125 - the
landing page every other dashboard page is reached from, plus one
per-document render and one per-concern detail page. "Variant C" from
the validated prototype (`prototype/dashboard-80`) - no persistent
sidebar or top bar, the landing page carries the navigation.

**The KPI row itself lives in `dashboard/kpi_section.py`** (split out
once this file crossed file-size-audit's WATCH threshold, ticket #176) -
`KpiContext`/`source_content`/`source_json` re-export or import from
there; see `docs/dev/dashboard/kpi_section.md`.

## DashboardRunContext

`write_dashboard`'s own bundle - `kpi_context` plus `site`/`out_dir`,
kept out of `KpiContext` itself since those two are about identity and
location, not metrics.

## _graph_card

The landing page's own top-level Graph card (ticket #163, map #159) -
alongside the concern grid, not inside it, per the map's own charting
decision (a dedicated card, more discoverable than being buried under
the `export` concern's own detail page, which still exists unchanged
too - this is additional, not a replacement). Reads "not available this
run" the same way a KPI tile does when `export.json` wasn't produced.

## _concern_page

A card per file (ticket #177, map #172 - was a bare `<ul>`), plus
`document_context.py`'s own real "what is this document typically used
for" explanation surfaced here, before a reviewer opens any specific
file - not only after, the way it already showed on the document's own
detail page (ticket #145). One shared rendering (`render_context_section`)
for both.

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
files directly. `dashboard/graph.html` is added only when `export.json`
was actually produced this run (ticket #163) - no page for the Graph
card to link to otherwise, matching every other "not available this
run" document already gets.

## write_dashboard

The one impure entry point - reads every produced document's content
back off disk (the only content `run_document_pipeline`'s own return
value doesn't carry, only paths and metadata), then writes
`build_dashboard`'s result.
