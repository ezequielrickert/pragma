# `src/generators/component_tree.py`

## module

Phase 5 of the crawl4ai migration: a deterministic ASCII/Unicode
component-tree document, separate from `GraphPRDSynthesizer`'s prose
"Digital Blueprint" - written to its own output file, never merged into
or replacing it.

First level: every crawled page, labeled by its own `<title>` (Phase
2). Second level: every component discovered on that page (Phase 0's
ghost-node fix is what makes this level trustworthy at all) plus every
static text block (Phase 4) as a distinct leaf kind - never nested
further, so a redirect target is rendered as a reference back to its
own first-level entry, not an inlined subtree (the flat "first level:
endpoints, second level: components" shape this whole feature was asked
for specifically avoids the graph-vs-tree cycle a literal nested
rendering would hit).

The tree *structure* is built and rendered entirely deterministically -
`build_component_tree`/`render_ascii_tree` never call an LLM. This was
an explicit, deliberate choice (not merely "simpler"): an LLM asked to
reproduce structured data as precisely-formatted text risks silently
smoothing over or fabricating exactly the kind of gap the ghost-node
bug (Phase 0) already showed can hide in this data undetected. AI
narration stays optional and out of this module entirely - if ever
added, it must get its own dedicated `system_instruction`, never shared
with `CATALOG_SYSTEM_INSTRUCTION`/`SYNTHESIS_SYSTEM_INSTRUCTION`, per
wiki/prompt-engineering-for-llm-agents.md Principle 1.

## _format_variants

Reuses the same three-shape disambiguation `graph_prd_synthesizer.py`'s
catalog narration already relies on, so both consumers interpret the
raw `options` JSON blob identically.

## build_component_tree

No rendering, no AI. Kept separate from `render_ascii_tree` so the
*structure* is independently unit-testable (assert on `TreeLeaf` field
values) without coupling tests to exact box-drawing characters.

## redirect_index

A component's own last interaction's `resulting_url` is the primary
redirect-target source, since it's already local to the ledger entry.
`PageVisitor.visit` calls `sink.record_interaction(...)` and
`sink.record_navigation_edge(...)` back-to-back from the identical
`new_key` for any navigating interaction, so the two must never
disagree by construction - a real disagreement would itself be a
persistence bug to investigate, not a data-quality gap to paper over
silently.

## render_ascii_tree

No `GraphStore`/AI access at all. Two calls against identical input
produce byte-identical output regardless of anything else happening in
the process - this is what "rendered deterministically by code, not by
an LLM" cashes out to concretely.

## generate_component_tree_document

Mirrors `GraphPRDSynthesizer.synthesize()`'s own "one function, no
further ceremony" shape.
