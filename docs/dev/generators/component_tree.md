# `generators/component_tree.py`

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

## _build_option_redirects

Since `GraphStoreSink._record_choice_group` (2026-08-11) collapses a
dropdown/menu/radio/checkbox group into one `Component` node, a specific
choice's own outcome (it navigated somewhere its siblings didn't, e.g.
"Large" leading to a size-details page the others don't) no longer has
its own leaf to show up on - that fact now lives in the group's single
node's `interactions`, tagged with `source_path` (see
`docs/dev/core/interfaces.md#record_component_interaction`). This
function is where it resurfaces: one line per interaction that carries a
`source_path`, resolved back to its choice's `text` via
`component_classifier.choice_text_by_path`. Only applies to
`choice_group`; `revealed_options` never carries a
per-choice `path` to resolve against (see
`component_classifier.md#describe_options`), so it's skipped there, same
as `stepper`.

Empty for any leaf that isn't a consolidated group's representative, or
whose group was never individually interacted with beyond its
representative - the ordinary case, unaffected.

## redirect_index

A component's own last interaction's `resulting_url` is the primary
redirect-target source, since it's already local to the ledger entry.
`PageVisitor.visit` calls `sink.record_interaction(...)` and
`sink.record_navigation_edge(...)` back-to-back from the identical
`new_key` for any navigating interaction, so the two must never
disagree by construction - a real disagreement would itself be a
persistence bug to investigate, not a data-quality gap to paper over
silently.

## region

A leaf's landmark region, or `""` for a leaf in none - which is also what
every leaf reports for a crawl recorded before structural containment
capture existed.

Text leaves never get one. Containment is recorded per interactive
component; assigning a text node to a region by proximity would be a guess,
and this document does not guess.

## regions

`build_component_tree`'s read of `get_component_regions()`. One store call
per document, not one per leaf.

## group_by_region

The nesting lives in the renderer, not in `TreePage`. A leaf knowing its own
region is a fact about the leaf; nesting is a way of showing it. Keeping the
built tree flat means `build_component_tree` stays a straight read and every
caller that just wants "every leaf on this page" - including the component
and text counts in the document header - still gets it without walking two
levels.

Named regions sort first, alphabetically; leaves in no region come last
under `""`. A page where nothing is in a landmark renders with no header and
no extra indent at all, exactly as it did before this existed: a single
"(no landmark region)" line above every leaf on the page would be one more
level of indentation carrying no information.

## render_ascii_tree

No `GraphStore`/AI access at all. Two calls against identical input
produce byte-identical output regardless of anything else happening in
the process - this is what "rendered deterministically by code, not by
an LLM" cashes out to concretely.

A leaf's `option_redirects` (see `_build_option_redirects` above) render
as their own indented sub-lines directly beneath that leaf's own line,
one level deeper than the leaf itself - a grandchild in the tree, not a
sibling component and not folded into the leaf's single line the way
`redirect_target`/`variants`/`requests` are.

## generate_component_tree_document

Mirrors `GraphPRDSynthesizer.synthesize()`'s own "one function, no
further ceremony" shape.

## ComponentTreeDocument

`DocumentGenerator` adapter, same placement reasoning as
`graph_prd_synthesizer.md#prddocument`.

Note the inversion: config carries `tree_ascii` (opt *in* to ASCII) while
`generate_component_tree_document` takes `use_box_drawing` (opt *out*).
The adapter is where the two meet, so neither side had to change its own
sense to accommodate the other.
