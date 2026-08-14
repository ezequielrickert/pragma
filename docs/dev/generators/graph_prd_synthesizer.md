# `generators/graph_prd_synthesizer.py`

## module

Phase 5 of the crawl4ai migration: post-hoc PRD synthesis from
`GraphStore`.

With Neo4j (or `InMemoryGraphStore`) as the crawl's primary source of
truth (Phase 3), this is the step that reads it back and produces the
final markdown blueprint - the same output artifact
`SimplePRDGenerator.generate_prd` produced, but sourced entirely from
persisted graph state rather than an in-process research log. Runs
independently of any live crawl: given a `site` whose graph was
populated by an earlier `MechanicalCrawler` run (or even one from
hours/days ago against a persisted Neo4j store), `synthesize()` needs
nothing else.

Three-stage map-reduce synthesis - not the two-stage shape this module
used to have. **Update - the original two-stage design (per-page
narration, then one single aggregate call over every page) turned out
to be exactly the unbounded-prompt bug
wiki/local-and-small-model-constraints.md already warned about, just
never ported here from the now-deleted `SimplePRDGenerator`'s
`batch_size`-capped prompt construction:** confirmed live on
empanad.app (see docs/explicativos/avance-corridas-gemma-empanadapp.md)
- the single final `agent.generate()` call, built from every page's
full narrated component catalog plus the entire Mermaid navigation
graph with no size cap at all, hit `finish_reason: "length"` 4/4 times
even at `max_tokens: 8192`, crashing the whole run with zero `docs/`
output despite the crawl itself completing successfully every time.
Now: **map** (one bounded call per page, unchanged), **batch-summarize**
(one bounded call per `batch_size`-sized group of pages, producing a
short section summary), then **reduce** (one small final call over only
the already-condensed section summaries, never the raw per-page facts
again - bounded regardless of site size). The Mermaid graph is rendered
deterministically and appended to the output in code, never asked of
the model - `build_mermaid_graph` already does this without an LLM
call, so asking the model to reproduce it verbatim inside its own
completion only spent real output-token budget on exactly the
highest-risk call for nothing.

Each stage gets its own `system_instruction`, per
wiki/prompt-engineering-for-llm-agents.md Principle 1 - none are shared
with each other or with the fill-value call (Phase 4).

## SYNTHESIS_SYSTEM_INSTRUCTION

Used by the batch-summarize stage: summarizes one bounded group of
pages' facts into a short section. Kept under its original name (still
imported by existing tests/callers) even though its job shifted from
"summarize every page in the site" to "summarize one batch of pages" -
the instruction text itself describes the batch-scoped job now.

## REDUCE_SYSTEM_INSTRUCTION

Used by the reduce stage: combines several already-condensed section
summaries (never raw per-page facts) into the Blueprint's overall
narrative. Deliberately its own instruction, not shared with
`SYNTHESIS_SYSTEM_INSTRUCTION` above - "summarize condensed summaries"
is a structurally different task from "summarize raw facts," per
wiki/prompt-engineering-for-llm-agents.md Principle 1.

## _build_page_facts

One catalog-ready fact dict per distinct control on a page, collapsing
a stepper's increment/decrement/value trio or a choice-group's N
members into a single entry - matches the `options` JSON shape
`GraphStoreSink.record_inventory` actually persists (Phase 3), not the
older `SimplePRDGenerator._build_page_catalog_facts`'s schema, since the
two were never the same data source (see `module` above). Since
2026-08-11 this collapse is no longer just a dedup of what would
otherwise be N redundant facts (`seen_choice_groups`) - the ledger
itself only ever has 1 node for the whole group now (see
`docs/dev/spiders/graph_sink.md#record_inventory`), so there's only
ever 1 to iterate in the first place.

The three-shape `options` disambiguation itself lives in
`component_classifier.py::describe_options` - shared with
`component_tree.py`'s deterministic renderer (Phase 5) rather than
duplicated. `revealed_options` (Phase 1's dropdown-variant capture) has
no branch here - it falls through to the generic case below, unchanged
from before this field existed - `component_tree.py` is where revealed
options actually get surfaced; this function's job is narration text,
not a full inventory of every options shape.

## _choices_leading_elsewhere

A `choice_group` fact's `leads_elsewhere` (present only when non-empty):
`"choice text -> resulting_url"` for every consolidated member whose own
interaction navigated somewhere, resolved back to its choice's label via
`component_classifier.choice_text_by_path` (shared with
`component_tree.py`'s identical need). The one thing a group's single
node must not let the LLM
catalog narration miss just because 5 nodes became 1: a choice behaving
differently from its siblings (e.g. one dropdown option leading to a
details page the others don't) is still a fact worth writing prose
about.

## GraphPRDSynthesizer

Writes nothing back to `GraphStore` - the inverse of `MechanicalCrawler`.

## batch_size

Pages per batch-summarize call (see `_summarize_batches`). Default kept
small deliberately: each "item" here is a full page block including its
already-narrated component catalog - much heavier per item than a short
label, so this is a more conservative budget than a typical crawl-time
`batch_size` knob. See `module` above for why this exists at all.

## _narrate_page_catalog

One `agent.generate()` call per page (batched across all of that page's
components, not one call per component - same small-model-conscious
discipline wiki/local-and-small-model-constraints.md established). A
narration failure on one page degrades to its raw facts rather than
aborting the whole catalog - documentation enrichment, not something
correctness depends on.

## _summarize_batches

Group `page_lines` into `self.batch_size`-sized chunks and produce one
bounded `agent.generate()` call per chunk - the fix for the unbounded
"every page in one prompt" call this module used to make (see `module`
above). A batch failure degrades to its raw page lines rather than
aborting the whole run, matching `_narrate_page_catalog`'s existing
degrade-not-abort discipline.

## _reduce

Combine already-condensed section summaries into the Blueprint's
overview narrative - one small call, bounded regardless of site size
since it never sees raw per-page facts, only the summaries above.
Degrades to a plain concatenation under simple headers on failure,
rather than crashing the whole run and writing zero output (the actual
empanad.app symptom `module` above describes).

## synthesize

The only method callers need. Reads, in order: the page/route table,
the navigation edges, per-page component narrations (derived from the
ledger), and recorded page descriptions - then a bounded map-reduce
pass (batch-summarize, then reduce) over the aggregate. See `module`
above for why this replaced the old single unbounded call.

## PRDDocument

The `DocumentGenerator` adapter, kept in this file rather than a separate
`prd_document.py` for the same reason agents and graph stores register
themselves next to their implementation: the registration and the thing
being registered stay in one place, and `bootstrap.py` importing this
module is what makes `"prd"` resolvable.

It is a thin adapter on purpose - `GraphPRDSynthesizer` keeps its own
constructor and its `synthesize(site)` entry point, so every existing test
and any direct caller is untouched by the pipeline landing.
