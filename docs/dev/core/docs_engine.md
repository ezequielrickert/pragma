# core/docs_engine.py

## module

`pragma docs`'s own entry point: docs-only generation from an existing
site DB, no re-crawl. Deliberately its own class, not a mode on the
crawl engines - `pragma static`/`pragma dynamic` always drive a real
crawl, and neither has a "just read what's there" mode. `pragma docs`
sidesteps that gap entirely rather than fixing it: it never touches
`Crawl4AICrawler` or either phase command's engine at all, only the
graph store `pragma static` (and, if they ran, `pragma cluster`/`pragma
dynamic`) already wrote. Absorbs
`analysis/graph_projection_apply.py::apply_graph_projection` and the
semantic-tier derivation passes (`_apply_data_model`/`_apply_rules`/
`_apply_screens`/`_apply_flows`) as its own internal steps, since
nothing but doc generation consumes either's output - inherited from
the retired Legacy Engine (`core/engine.py`, issue #242) rather than
redesigned, since `pragma docs` needed exactly what that engine already
did after its own crawl finished.

## docsrunresult

The output documents from one docs-only pass - same shape as
`EngineRunResult`'s own `documents` field, minus the crawl-specific ones
(`export_path`/etc. aren't named fields here, just members of
`documents` like everywhere else).

## DocsRunResult.dashboard_path

Added in ticket #125 (ADR-0016 Phase C): the dashboard's own entry
point, `dashboard/index.html` under `out_dir` - distinct from
`index_path`, which is `generate_docs_index`'s cross-run Markdown index
built from `runs.json`, a different concern (which past runs exist)
than the dashboard's own (what does *this* run's crawl look like).

## docsengine

Wires an agent and a graph store, then generates documents from
whatever that store already holds.

## from_config

Resolves the agent and graph store named in `config`, scoped to `site` -
a bare host/slug, not a URL, since `pragma docs` reads an existing site
a previous `pragma static` run already wrote rather than crawling one of
its own. Same convention `ClusterEngine.from_config` uses.

## run

Projects the navigation graph, derives the semantic tier
(`_apply_data_model`/`_apply_rules`/`_apply_screens`/`_apply_flows`,
each a whole-site pass over whatever the store already holds), then
generates every configured document from `site`'s existing graph store
- no crawling. Works against a `static`-only DB: `pragma cluster`/
`pragma dynamic` having run is a richer input, not a requirement - an
empty component ledger just means each pass derives nothing.
`stopped_reason` is always `""` - no crawl happened in this process, so
there is no partial-run reason to report.

`run_id` is generated fresh here (unlike the crawl engines, which stamp
one before crawling starts) since a docs-only pass has no crawl to tie
it to - it exists purely to mark which run's semantic-tier derivation
produced a given `DERIVED_FROM` edge.

Once every document is written, builds the dashboard
(`dashboard.shell.write_dashboard`, ticket #125) from the same
`produced` list and the same `finished_pages`/`total_pages`/
`unexplored_components`/`total_components` this method already computed
for `record_run_manifest` - passed straight through as `KpiContext`
rather than a second, independently-derived count.

## _apply_data_model

Deduces the semantic tier's `Entity`/`Field` set from the forms the crawl found
and writes it back with its provenance.

Whole-site rather than per-page for the same reason family clustering is: the
derivation groups components by the form they sit in, and a live per-page write
stream cannot see a form whose inputs arrived across two visits.

**No error handling of its own, deliberately.** `record_entities` raises on a
node with no provenance, and a raise here means the derivation produced an
unsupported assertion - a bug to fix, not a document to degrade.

## _apply_rules

One `Rule` per declared single-field constraint, plus one per `<select>`'s
declared option set (`generators/rules.py::build_rules`) - the semantic
tier's fourth writer, alongside `_apply_data_model`/`_apply_screens`/
`_apply_flows`. Must run after `_apply_data_model`: `record_rules`'s
`GOVERNS(Rule->Field)` edge is resolved through the `Field`/`EDITS` data
`record_entities` writes, over the same component population. Same
no-error-handling reasoning: `record_rules` raises on a rule with no
`derived_from`, which `build_rules` always sets from the constraint's own
source component.

## _apply_screens

One `Screen` per finished `Page` (`generators/screens.py::build_screens`),
narrated with a name/purpose (`generators/screen_narrator.py::narrate_screens`),
written back with its provenance - the semantic tier's second writer,
alongside `_apply_data_model` above. Same no-error-handling reasoning:
`record_screens` raises on a screen with no `page_url`, which `build_screens`
always sets from a real `Page.url`.

## _apply_flows

One `Flow` per trace the crawl walked (`generators/flows.py::build_flows`),
written back with its provenance - the semantic tier's third writer,
alongside `_apply_data_model` and `_apply_screens` above. No narration step,
unlike `_apply_screens`: the derivation research (issue #186) found
`Flow.name`/`goal` fully templatable, so this pass needs no `Agent`. Same
no-error-handling reasoning: `record_flows` raises on a flow with no
`derived_from`, which `build_flows` always sets from the trace's own steps.

## _document_names

The configured list, plus `"export"` when `export_json` is on and the
list didn't already ask for it.
