# `core/engine.py`

## module

Post-crawl4ai-migration: `run()` is two steps, not one -
`MechanicalCrawler.crawl_site()` writes only to `GraphStore` (via
`GraphStoreSink`), then `GraphPRDSynthesizer.synthesize()` reads only
from `GraphStore` to produce the final markdown. `Crawl4AICrawler`/
`MechanicalCrawler`/`GraphPRDSynthesizer` are wired directly here rather
than through a registry - unlike agents/graph stores, there's exactly
one crawling implementation now.

## EngineRunResult

`Engine.run()`'s return value - the output documents from one crawl, per
the component-tree feature's explicit "separate output file, not merged
into the existing prose PRD" requirement, extended the same way for the
(opt-in) JSON export.

`export_path` is `None` whenever `export_json` is off (the default) -
callers should treat `None` as "not generated this run," not as a
failure. `manifest_path` is always set: recording this run in
`docs/runs.json` (`utils/io.py::record_run_manifest`) is
unconditional, unlike the export - it's cheap bookkeeping, not an extra
artifact someone has to opt into.

## EngineRunResult-index_path

`docs/index.md` - a browsable Markdown index of every run recorded in
the manifest, regenerated fresh on every run (Fase E,
`utils/io.py::generate_docs_index`). Always set, same as
`manifest_path` - this is bookkeeping over `runs.json`, not an opt-in
artifact.

## __init__-crawl-timeouts

See `PragmaConfig`'s matching fields / `Crawl4AICrawlerConfig`'s doc for
what each of these actually changes and their tradeoffs
(`page_timeout_seconds` bounds a different phase than `wait_seconds`;
`prefetch` empties debug markdown snapshots; `block_images` is a real
behavior change some sites may depend on). `interaction_timeout_seconds`
is a third timeout phase, distinct from `page_timeout_seconds` - see
`Crawl4AICrawlerConfig`'s own entry for it. `navigation_watchdog_seconds`
is a fourth, independent of all three - an outer backstop around every
`arun()` call rather than a bound on any one internal phase of it - see
`docs/dev/core/config.md#navigation_watchdog_seconds`.
`session_cleanup_timeout_seconds` is a fifth, guarding a distinct,
separately-confirmed deadlock site (periodic session recycling via
`close_session`, not navigation) - see
`docs/dev/core/config.md#session_cleanup_timeout_seconds`.

## __init__-two_phase_crawl

Passed straight through to `MechanicalCrawlerConfig.two_phase_crawl` -
see `PragmaConfig`'s own `two_phase_crawl` entry
(`docs/dev/core/config.md#two_phase_crawl`) and
`docs/dev/spiders/orchestration/mechanical_loop/config.md#two_phase_crawl`
for what it actually changes. `Engine` itself makes no decision about
it - just wiring, same as every other `MechanicalCrawlerConfig` field
threaded through here.

## __init__-allow_subdomains

A link (or a redirect a click lands on) that leaves this crawl's own
site is out of scope and never itself visited, even though the
interaction/edge that led there is still recorded. See
`MechanicalCrawlerConfig`'s own `base_url`/`allow_subdomains` entries and
`utils/urls.py`'s `is_in_scope()` for what "same site" means here.

## __init__-ai_fill_values

`False` skips the per-fillable-field AI call entirely (falls back to
`MechanicalCrawler`'s fast deterministic placeholder) - the AI call is a
real network+generation round trip per field (more so for a remote/local
model), worth cutting for a speed-focused run that doesn't need
realistic fill values in the output.

## run

Synchronous entry point (unchanged shape for the CLI) bridging to the
async crawl underneath via `asyncio.run` - crawl4ai owns an async
browser lifecycle, but nothing above `Engine` needs to know that.

## _apply_component_families

Runs once per `_run_async` call, after `mechanical.crawl_site` returns
and before `GraphPRDSynthesizer.synthesize` reads the graph - component-
family clustering needs to see every component the whole crawl found at
once (`component_family.py`'s `build_component_families` has no
incremental/streaming mode), unlike everything `GraphStoreSink` writes
live during the crawl itself. Flattens `get_component_ledger`'s
`{page_url: {path: {...}}}` shape into a flat list with `page_url`
folded into each record, since that's the shape
`build_component_families`/`tags_with_multiple_instances` expect -
the ledger's per-page nesting exists for `GraphPRDSynthesizer`'s
page-by-page narration, not for a whole-site pass like this one.

## _document_names

Reconciles the two ways a run can ask for the JSON export: the newer
`PragmaConfig.documents` list and the older standalone `export_json`
boolean. The flag wins by *addition*, never by removal - it can turn the
export on, and a run that lists `"export"` explicitly keeps it whether or
not the flag is set. Written as one small method rather than inline so the
back-compat rule has a name and a place to be tested.

## EngineRunResult-master_path

Always populated: the master document is written on every run, including
one where every other generator failed (it would then index nothing, which
is itself the useful signal). `prd_path`/`tree_path` degrade to `""` and
`export_path` to `None` when their generator was not requested or failed -
the pre-existing meaning of those fields, unchanged.

## EngineRunResult-documents

Every document the run wrote, in pipeline order with the master last. The
named fields (`prd_path`, `tree_path`, `export_path`, `master_path`) are
shortcuts into this same list, kept because existing callers and tests use
them; this is what a caller iterates when it wants all of them without a
branch per document.

Added when the CLI's end-of-run listing turned out to be the last place
still carrying one hardcoded line per output file - `coverage` and
`master` had landed in Fase 0 and simply never appeared on screen.

## _apply_graph_projection

Materializes the navigation graph into `networkx` and writes per-page metrics and
module assignments back onto each `Page`.

Independent of the other whole-site passes - it reads only `get_edges`, not the
component ledger - so it can run in any order relative to them. What it produces
was unreadable by any document until `get_page_metrics` existed; see
`docs/dev/database/ladybug/analysis.md`.

## _apply_data_model

Deduces the semantic tier's `Entity`/`Field` set from the forms the crawl found
and writes it back with its provenance.

Whole-site rather than per-page for the same reason family clustering is: the
derivation groups components by the form they sit in, and a live per-page write
stream cannot see a form whose inputs arrived across two visits.

**No error handling of its own, deliberately.** `record_entities` raises on a
node with no provenance, and a raise here means the derivation produced an
unsupported assertion - a bug to fix, not a document to degrade.

## known-purposes

Family purposes are read **before** `record_component_families` wipes them.

A family whose members did not change keeps its existing sentence rather than
buying it again from the model. That is what keeps a site crawled in short
resumable passes from re-narrating everything on every pass, and it is why
`family_signature` has to be content-based - see
`docs/dev/generators/component_family_narrator.md#family_signature`.

## sink-scope

The sink is constructed with the same `base_url`/`allow_subdomains` the frontier
gates on, so a link is judged in-scope identically whether it is being queued or
being recorded.

It also needs `run_id` before the crawl starts, since writes stamp it as they
happen - which is why that id is generated separately from the `run_timestamp`
used later for document filenames.

## stopped_reason

Read before the crawler goes out of scope, because every document has to be able
to say whether it describes a whole site or one budgeted slice of it.

It reaches the documents through `DocumentRequest.settings` and ends up in the
coverage banner, which is what makes a partial document look partial instead of
complete.
