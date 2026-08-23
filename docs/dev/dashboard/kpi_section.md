# `dashboard/kpi_section.py`

## module

The landing page's own crawl-wide metrics row (ADR-0016 point 4), split out
of `dashboard/shell.py` once it crossed file-size-audit's WATCH threshold
(ticket #176, map #172) - a real SRP seam: "what numbers does the landing
page show" is a different reason to change than `shell.py`'s own job of
assembling the landing/concern/document pages around it.

**Why KPI numbers come from several different places.** Pages/components
counts come from the caller's own already-computed `KpiContext` -
`core/docs_engine.py`/`core/engine.py` both already compute
`finished_pages`/`total_pages`/`unexplored_components`/`total_components`
locally for `record_run_manifest`; `coverage.json`'s own serialized JSON
shape doesn't expose `components_explored` at all (only
`interactions.detected`, a different number), so there's no file to read
this pair from anyway. Endpoints, requirement confidence, and usability/
accessibility finding totals do have a real dedicated source document
each (`coverage.json`, `confidence-summary.json`) - read from there, never
recomputed (ticket #175's own metrics-inventory research).

## KpiContext

The two counts `coverage.json` can't supply, passed through from the
caller rather than re-derived.

## source_content

The raw text of a `kind="source"` document, or `None` when a config
turned it off this run - the same "maybe absent" signal `manifest.json`'s
own `status: "off"` already encodes. `source_json` is this, parsed;
`dashboard/shell.py`'s own Graph card needs the raw text itself, not a
parsed dict, since `render_graph_page` embeds it directly - one shared
implementation, imported by both.

## source_json

`source_content`'s own text, parsed - `None` for the same "never
produced this run" case, plus `None` for text that isn't valid JSON.

## _kpitile

One tile's real display facts - `fraction` drives the radial ring
(`None` renders an empty ring for a metric with no natural denominator,
ADR-0001's own "saturating count" case, rather than a fabricated 100%).
`family` is the real `export.json` node `type` this metric maps onto,
where one exists.

## _safe_fraction

`numerator / denominator`, guarding both "either side missing" and an
honest zero denominator - a ring with nothing to show, not a crash.

## kpi_section

Assembles every tile: pages/components from `KpiContext`, endpoints from
`coverage.json`, requirement confidence from `confidence-summary.json`'s
own `prd` entry (leads with the real total, the observed/inferred/assumed
split as the tile's own secondary label), usability/accessibility finding
totals from that same document's own entries. Each tile with a real
`family` links to `graph.html?family=<Type>` when `graph_available` -
`dashboard/graph_assets.py`'s own `initialVisibleIds` reads that param.
Usability/accessibility never link - `Hallazgo` stays reserved (ADR-0002),
so a link there would always land on an empty family view.
