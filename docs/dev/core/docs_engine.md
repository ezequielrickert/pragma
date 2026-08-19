# core/docs_engine.py

## module

`pragma docs`'s own entry point: docs-only generation from an existing
site DB, no re-crawl. Deliberately its own class, not a mode on `Engine`
- `Engine._run_async` always drives a `MechanicalCrawler` crawl first,
and `MechanicalCrawler.crawl_site` always navigates, even against a
fully-crawled DB (there is no "just read what's there" mode). `pragma
docs` sidesteps that gap entirely rather than fixing it: it never
touches `Crawl4AICrawler` or `MechanicalCrawler` at all, only the graph
store `pragma static` (and, if they ran, `pragma cluster`/`pragma
dynamic`) already wrote. Absorbs
`analysis/graph_projection_apply.py::apply_graph_projection` as its own
first internal step, since nothing but doc generation consumes
projection output.

## docsrunresult

The output documents from one docs-only pass - same shape as
`EngineRunResult`'s own `documents` field, minus the crawl-specific ones
(`export_path`/etc. aren't named fields here, just members of
`documents` like everywhere else).

## docsengine

Wires an agent and a graph store, then generates documents from
whatever that store already holds.

## from_config

Resolves the agent and graph store named in `config`, scoped to `site` -
a bare host/slug, not a URL, since `pragma docs` reads an existing site
a previous `pragma static` run already wrote rather than crawling one of
its own. Same convention `ClusterEngine.from_config` uses.

## run

Projects the navigation graph, then generates every configured document
from `site`'s existing graph store - no crawling. Works against a
`static`-only DB: nothing here reads component families or the semantic
tier (confirmed by grep - `get_entities` has no caller outside its own
module and its tests), so `pragma cluster`/`pragma dynamic` having run
is a richer input, not a requirement. `stopped_reason` is always `""` -
unlike `Engine`, no crawl happened in this process, so there is no
partial-run reason to report.

## _document_names

Same contract as `Engine._document_names` - the configured list, plus
`"export"` when `export_json` is on and the list didn't already ask for
it.
