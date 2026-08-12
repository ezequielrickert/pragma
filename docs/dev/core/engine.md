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

`prd_path` and `tree_path` are `None` on a session that stopped early
with synthesis skipped (`_should_synthesize`). They are the same "not
generated this run" signal `export_path` already was, which is why the
CLI can guard all three the same way.

## EngineRunResult-stopped_reason

The `StopReason`'s string value, or `None` when the frontier drained and
the crawl of this site is genuinely complete. This is the fact the CLI
turns into a resume hint, and it is recorded in the run manifest so a
partial run in `docs/runs.json` is distinguishable from a complete one
that happened to find fewer pages.

## _SynthesizedDocuments

What one run's synthesis wrote, or nothing at all when it was skipped.
Exists so `_synthesize_documents` can return three related paths as one
named thing rather than a bare tuple whose ordering the caller has to
remember, and so the skipped case is a plain default-constructed value
instead of three separate `None`s threaded through `_run_async`.

## _catch_first_interrupt

Turns one Ctrl-C into a clean end-of-session instead of a traceback, and
returns the callback that undoes it.

Before this, a SIGINT during a crawl raised `KeyboardInterrupt` out of
`asyncio.run`; `cli.py` catches `Exception`, which that is not, so the
run died with a traceback, skipped the manifest, and never closed the
graph store. The crawl's *data* survived regardless - every page is
written to the store as it completes - but nothing recorded that the run
had happened at all.

The handler **removes itself as it fires**, so a second Ctrl-C aborts
immediately with the old behaviour. That is deliberate: the first
interrupt starts a grace period during which in-flight pages finish
(`crawlers/mechanical_loop.md#_wait_for_in_flight_pages`), and a user who
does not want to wait that out must not be trapped by their own stop
request.

`loop.add_signal_handler` is unimplemented on Windows' event loops, so
the `NotImplementedError` path installs nothing and returns a no-op -
Ctrl-C there behaves exactly as it did before.

## _seed_previous_frontier

Hands `MechanicalCrawler` whatever the last session left unfinished, when
`resume` is on. Reads `get_progress_table_rows` once and passes the rows
plus the start URL's scheme to `crawlers/resume_state.md#restore_frontier`
- the scheme because graph keys are `clean_url()` output and have had
theirs stripped.

A site with no recorded history yields an empty plan, which is reported
and skipped rather than treated as an error: `--no-fresh` on a site that
has never been crawled is a reasonable thing to type, and it should just
crawl.

## _should_synthesize

Whether to spend LLM calls narrating a crawl that may be partial.

`True` when the frontier drained, or when `synthesize_on_partial` forces
it. Otherwise the four whole-site passes are skipped and the reason is
printed with the command to resume. The cost argument is the whole point:
each pass re-reads the entire graph and narrates it, so running them on
every partial session means paying for the same site repeatedly, each
time describing a crawl that is not finished.

## _synthesize_documents

Runs every whole-site pass and writes the documents they produce.

Order is fixed and load-bearing: `apply_component_families` and
`apply_request_graph` write families and inferred requests *into* the
graph, and the PRD synthesis below them reads those back. This is the
same ordering the inline version had; extracting it into one function is
what makes "skip all of it" a single decision rather than four guards.

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

## whole-site passes

`apply_component_families` and `apply_request_graph` used to live here
and now live in `generators/whole_site_passes.md`. They moved out when
the stop/resume work pushed this file past the project's 500-line
threshold and an SRP read found the obvious seam: those two passes are
pure graph-in/graph-out post-processing that touch no `Engine` state at
all, and they change for different reasons than the crawl wiring around
them. `_synthesize_documents` calls them, in that order.
