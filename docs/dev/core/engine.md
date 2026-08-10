# `src/core/engine.py`

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
`docs/runs.json` (`src/utils/io.py::record_run_manifest`) is
unconditional, unlike the export - it's cheap bookkeeping, not an extra
artifact someone has to opt into.

## EngineRunResult-index_path

`docs/index.md` - a browsable Markdown index of every run recorded in
the manifest, regenerated fresh on every run (Fase E,
`src/utils/io.py::generate_docs_index`). Always set, same as
`manifest_path` - this is bookkeeping over `runs.json`, not an opt-in
artifact.

## __init__-crawl-timeouts

See `PragmaConfig`'s matching fields / `Crawl4AICrawlerConfig`'s doc for
what each of these actually changes and their tradeoffs
(`page_timeout_seconds` bounds a different phase than `wait_seconds`;
`prefetch` empties debug markdown snapshots; `block_images` is a real
behavior change some sites may depend on). `interaction_timeout_seconds`
is a third timeout phase, distinct from `page_timeout_seconds` - see
`Crawl4AICrawlerConfig`'s own entry for it.

## __init__-allow_subdomains

A link (or a redirect a click lands on) that leaves this crawl's own
site is out of scope and never itself visited, even though the
interaction/edge that led there is still recorded. See
`MechanicalCrawlerConfig`'s own `base_url`/`allow_subdomains` entries and
`src/utils/urls.py`'s `is_in_scope()` for what "same site" means here.

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
