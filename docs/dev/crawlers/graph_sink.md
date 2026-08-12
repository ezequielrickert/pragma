# `src/crawlers/graph_sink.py`

## module

Phase 3 of the crawl4ai migration: live `GraphStore` wiring for
`MechanicalCrawler` - Neo4j (or `InMemoryGraphStore`) becomes the crawl's
source of truth, written to as the crawl happens rather than batched by an
in-process orchestrator afterward.

Two small, separately-testable pieces:
- `GraphStoreInteractionTracker` - the `InteractionTracker` seam
  `interaction_tracker.py` already defines, backed by `GraphStore` reads
  instead of an in-memory dict, so "have I already interacted with this"
  survives across a persisted multi-run crawl, not just within one process
  (see wiki/graph-based-crawl-tracking.md's "the ledger must be consulted,
  not write-only"). Its `mark_interacted`/`mark_visited` never perform the
  real, detail-rich write - see their sections below - because
  `GraphStoreSink` below is what actually does that (with
  `action`/`value`/`resulting_url` the plain `InteractionTracker` protocol
  has no room for); routing a real write through here too would mean
  recording every interaction twice, once thin and once rich. They do,
  however, update this tracker's own local read cache (see
  docs/explicativos/plan-almacenamiento.md Fase B) - a cache update, not a
  second store write.
- `GraphStoreSink` - the detail-rich writer `MechanicalCrawler` calls
  directly at each point in the plan's hook-mapping table (page arrival,
  full component/link inventory, each interaction, navigation edges, page
  completion).

`GraphStoreSink` also owns `_representative_for` (2026-08-11): a
per-page `{member_path: representative_path}` map built by
`record_inventory` whenever it collapses a dropdown/menu/radio/checkbox
group into one `Component` node, and consulted by `record_interaction`/
`record_component_network` to redirect a later write on any of that
group's members onto the same node instead of creating a new one. See
`record_inventory`/`_record_choice_group`/`_resolve_write_path` below.

## _option_labels_for

`format_option_choices(describe_options(options_json))` in one call -
the clean, human-readable projection of one `options` JSON blob (e.g.
`["Mi Gusto (selected)", "Solo Empanadas", ...]`), computed at write
time and stored as `option_labels` alongside the raw JSON on the same
`Component` node. Called from all three `record_component_options`
sites (`record_inventory`'s stepper write, `_record_choice_group`,
`record_revealed_options`) so every options write gets this second,
clean field for free, without needing external tooling
(`component_tree.py`'s rendered `.md`) just to read a choice list back.

## _component_facts

Pure mapping from one raw, JS-discovered component dict
(`discover_components.js`'s per-element shape - `attributes`/`style`
nested dicts, plus top-level `placeholder`/`label`/`name`/`disabled`/
`required`/`form`) onto `GraphStore`'s `ComponentFacts`
(`docs/dev/core/interfaces.md#ComponentFacts`), added 2026-08-11. Kept as
a standalone function rather than inlined into `_write_component` so the
attribute/style field-name mapping - the part actually at risk of a
left-side/right-side typo - has its own direct unit test
(`tests/test_graph_sink_component_facts.py`) that doesn't need a real
browser round-trip to exercise.

No I/O, no `GraphStore` dependency - same "pure function, no side
effects" placement as `component_classifier.py`'s own functions.

## GraphStoreInteractionTracker

`InteractionTracker` backed by `GraphStore` reads, with a per-instance
local cache (docs/explicativos/plan-almacenamiento.md Fase B - "the N+1
read pattern" finding).

**Why the cache exists**: `GraphStore.get_component_states` is documented
(see its docstring on `GraphStore`) as "one query per page visit, not one
per component" - but before this cache, `is_interacted` called it fresh
on *every single call*, and `PageVisitor.visit`'s frontier loop calls
`is_interacted` once per component considered, every pass - so a page
with N components did N full `GraphStore` round-trips (network
round-trips for `graph_store: neo4j`) just to answer the same "have I
interacted with this yet" question the loop already asked moments ago
for a barely-changed page. This directly contradicted the documented
"one query per page visit" contract rather than merely being slow by
coincidence. `is_visited` had the same shape for `_enqueue`/`_worker`
(called once per discovered link / per dequeue). Caching turns both into
one real `GraphStore` read per page for the lifetime of this tracker
instance (one per `MechanicalCrawler`, i.e. one per crawl) instead of one
per check - a real reduction in `GraphStore` round-trips, and (for
`graph_store: neo4j`) a real reduction in how often this crawl's own
event loop is blocked waiting on the synchronous Neo4j driver (see the
plan doc's Fase B section for why eliminating that blocking *entirely*
was scoped out of this change - it would require awaiting through
methods explicitly documented as synchronous by design, e.g.
`PageVisitor._transition_to_new_state`).

**Why this is safe** (no interface/behavior change from
`MechanicalCrawler`'s point of view - same sync methods, same signatures,
same semantics): every real write this crawl makes to
"interacted"/"visited" state goes through
`mark_interacted`/`mark_visited`, called at the *same* call sites as the
paired `GraphStoreSink.record_interaction`/`record_page_finished` real
writes - so the cache is updated in lockstep with the real store, for
every write *this* tracker instance's crawl performs. A path never seen
before (new to this page's cache, e.g. a just-revealed component)
correctly falls through to "not interacted" via a plain dict miss -
identical to what a fresh `GraphStore` read would say for a path that was
never written. The only actor that could make this cache stale is a
*different* process/tracker instance writing to the same site
concurrently while this crawl runs - not a new risk this cache
introduces: the existing architecture already assumes
single-writer-per-site-per-crawl (see `PragmaConfig.fresh`/`clear_site`'s
own docstring).

## mark_interacted

Never the real write - `GraphStoreSink.record_interaction` is what
actually calls `GraphStore.record_component_interaction` for every
attempted interaction (success or failure), with the full
`action`/`value`/`resulting_url` detail this protocol method doesn't
carry. Updates this tracker's own local cache only, so a same-pass
re-check of the same path (e.g. the frontier loop revisiting a path
already marked earlier in this same pass) sees it without a redundant
`GraphStore` round-trip - `dict.setdefault` rather than requiring the
path to already be cached, since a component can be marked interacted
(e.g. a failed-interaction path, or one auto-created via
`record_component_interaction`'s own `ON CREATE`) without ever having
gone through `record_component`/being present in an already-cached
page's initial read.

## mark_visited

Never the real write - `GraphStoreSink.record_page_finished` is what
actually calls `GraphStore.upsert_page(..., status="Finished", ...)` -
see that method's section below for why it needs the final component
count, which this protocol method doesn't carry. Updates the local cache
only, same reasoning as `mark_interacted` above.

## GraphStoreSink

Writes a `MechanicalCrawler` crawl's facts into `GraphStore` as they
happen. Every method maps directly to one row of the plan's "which
crawl4ai hook maps to which GraphStore call" table, just invoked from
`MechanicalCrawler`'s own Python-side orchestration (not a crawl4ai hook
itself) since it needs the actual interaction *result* (did the URL
change), which only exists once `crawler.click()`/`fill()` returns.

## record_page_arrival

Cheapest possible "this page exists" signal - called the moment a page
is reached, before discovery/interaction. A bare rediscovery
(`status="Pending"`) never clobbers an already-Finished page, per
`GraphStore.upsert_page`'s own contract - same discipline now applies to
`description` (added for the PRD synthesizer, which reads it back via
`get_page_descriptions` instead of an in-process attribute that would
die with the crawling process) and to `title` (the page's own `<title>`,
read back via `get_page_titles` - the document renderer's "name of this
page," distinct from `label`'s per-incoming-link anchor text).

## record_text_content

Full, unconditional static-text inventory - called once per page visit
(see `PageVisitor.visit`), not re-called on same-page reveals the way
`record_inventory` now is for `Component` (see
`GraphStore.record_text_content`'s docstring for why that's a
deliberate, documented cut rather than an oversight).

## record_inventory

Full, unconditional component + link inventory for one discovery pass -
every *ungrouped* component gets a `record_component` call (idempotent,
safe to call again on rediscovery) regardless of whether anything on it
changed, mirroring the old `_record_page_inventory`'s "unconditional, not
gated by any per-turn cap" discipline. Detected steppers get their
structured facts attached via `record_component_options`, reusing
`component_classifier.py` unchanged - the same deterministic, no-LLM
classification the old catalog narration pass already relied on.

A *grouped* component - a member of `group_choice_sets` (radio/checkbox
sharing a `name`) or `group_option_families` (a dropdown/menu's
`role="option"`-family siblings, new 2026-08-11) - never gets its own
`record_component` call at all. Instead `_record_choice_group` writes
exactly one representative node per group (real tag/text/component_type,
not a blank stub - see `_write_component`) carrying the whole group's
choices as one `options` JSON blob. This is a deliberate node-count
reduction: before this, a 5-choice dropdown produced 5 near-identical
`Component` nodes differing only by which choice they are; now it
produces 1. See `component_classifier.md#group_option_families` for why
`role="tab"` is excluded from this collapse.

## _write_component

One component's descriptive fields -> `GraphStore.record_component`.
Factored out so the main inventory loop and `_record_choice_group`'s
representative write go through the exact same code - a group's
representative node gets real fields the same way an ordinary ungrouped
component does, never the `_COMPONENT_BLANK_STUB` ghost-node shape
(the 2026-08-08 bug this file's regression test used to guard narrowly
against 3 separate option nodes; it now guards 1 consolidated one).

Also passes `facts=_component_facts(comp)` (2026-08-11) - a group's
representative gets the *representative member's own* attributes/style,
same as its tag/text/component_type; the other members' facts are not
separately recorded (they never had their own `Component` node to begin
with, same as their tag/text).

## _record_choice_group

Persists one member-list (a `group_choice_sets`/`group_option_families`
group) as a single `Component` node. `members[0]` is the representative:
its own path becomes the node's identity, and every member's path -
including the representative's own - gets recorded into
`_representative_for` for `_resolve_write_path` to redirect later writes
to.

## _resolve_write_path

Where a path's write actually lands, and which exact member caused it.
Called by `record_interaction`/`record_component_network` before every
write: a path that `_record_choice_group` grouped redirects to its
group's representative node instead of creating its own (the whole point
- an option that only gets *clicked*, not just discovered, must still
not spawn a fresh node); an ungrouped path, or the representative's own
path, passes through unchanged. Returns `(write_path, source_path)` -
`source_path` is `""` unless a redirect happened, in which case it's the
original path, so which specific choice acted is relocated onto the
representative's own interaction record, never silently lost. See
`component_tree.md#_build_option_redirects` for where that fact
resurfaces in the generated output.

## record_interaction

One call per *attempted* interaction (success or failure) - the
component-level ledger's whole value is knowing what was tried, not just
what worked. `resulting_url` is `""` for a failed interaction (nothing to
report) or a same-page one (no navigation). Redirects through
`_resolve_write_path` first - see above.

## record_component_network

One call per interaction that triggered ≥1 meaningful (xhr/fetch) network
request (see `src/crawlers/network_filter.py`) - the "request
information" a real JS/SPA site's submit-like control needs, since it has
no static `<form method/action>` to read instead. Redirects through
`_resolve_write_path` first; when redirected, each request dict in the
batch gets a `source_path` key added before serializing, same reasoning
as `record_interaction`.

## record_revealed_options

Attach a before/after-diff-detected set of newly revealed
`role="option"`-family components (`component_classifier.
find_revealed_options`) to the *trigger* component's `options` field -
the click that opens a combobox/listbox doesn't carry its own choices in
any single discovery snapshot, unlike every other field
`record_component` refreshes; they only exist once the widget has
actually been opened. Mirrors `group_steppers`/`group_choice_sets`' own
`record_component_options` call in `record_inventory` above, but keyed by
the specific interaction that produced it rather than a single-snapshot
classification, since this fact genuinely isn't derivable from one
snapshot alone.

## record_navigation_edge

Only called when an interaction's resulting URL differs from the page it
was attempted on - a real navigation, not a same-page reveal.

## record_page_finished

Called once a page's interaction pass completes *without* being cut
short by a navigation (see
`PageVisitResult.interrupted_by_navigation`) - an interrupted pass
leaves the page genuinely incomplete, so it must stay `Pending` for its
guaranteed follow-up pass, not be marked `Finished` prematurely.
