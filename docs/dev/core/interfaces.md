# `core/interfaces.py`

## module

Post-crawl4ai-migration: the per-step decision vocabulary that used to
live here (`Action`/`AgentAction`/`TOOL_SPECS`/`parse_agent_action`/
`Agent.act()`) is gone along with the per-step LLM decision loop it
served - there is no longer a numbered "Clickable elements" list for a
model to pick from, since `MechanicalCrawler`
(`spiders/orchestration/mechanical_loop.py`) interacts with every discovered
element mechanically. `Scraper`/`PRDGenerator` are gone too: they
modeled a synchronous, lazily-started, single-`Page`/single-call-return
shape that doesn't fit `Crawl4AICrawler`'s async, `AsyncWebCrawler`-owns-
the-browser-lifecycle model, or the new crawl()-then-synthesize() split
(see `Engine`). `PageState`, `Agent` (now just `generate()`), and
`GraphStore` remain - the contracts that are still genuinely shared
across implementations.

**Update (2026-08-12)**: `PageState`/`ComponentFacts`/`ComponentFamily`/
`InferredRequest` - the plain data contracts, as opposed to `Agent`/
`GraphStore`'s actual interfaces - moved to `data_contracts.py` once this
file crossed the 500-line file-size-audit threshold. Re-exported from
here unchanged (`from .data_contracts import PageState, ...`), so every
existing import site elsewhere in the codebase needed no changes. See
`data_contracts.md#module` for the full reasoning.

## PageState.description

Short (~300 char) description of what this page is about - meta
description if the site has one, else heading + first substantial
paragraph. `""` for backends/tests that don't extract it. See
`page_extraction.run_extraction` for how this is built and
`GraphStoreSink.record_page_arrival`/`GraphStore.get_page_descriptions`
for how it ends up in the final PRD via `GraphPRDSynthesizer`.

## PageState.network_requests

Meaningful (xhr/fetch) network requests triggered by the interaction that
produced this `PageState` - see
`spiders/content/network_filter.py::filter_meaningful_requests` for exactly
what "meaningful" means and what each dict contains. Always `[]` for a
plain navigation (`Crawl4AICrawler.discover_page` never enables capture -
a page load's own requests aren't attributable to one component's
interaction the way a click/fill's are); only populated by
`Crawl4AICrawler._interact`.

## PageState.text_content

Non-interactive prose (`<p>`/`<h1-6>`/`<li>`/...), captured once per page
visit alongside `components` - see `spiders/content/js/extract_text_content.js`
for exactly what's captured and excluded (anything that's an interactive
component's own label text). Each entry: `{tag, text, path, visible, rect}`.

## ComponentFacts

DOM-attribute and computed-style facts about a discovered element, added
2026-08-11 alongside `discover_components.js`'s `attributes`/`style`
fields (`spiders/content/js/discover_components.js`'s `getStyleFacts`)
finally getting persisted instead of being computed and discarded before
reaching `record_component`. Bundled into one dataclass rather than
fifteen more scalar params on `record_component` itself - that method
already took thirteen; growing it further one field at a time would
violate `python-clean-code`'s F1 (max 3 args, use a dataclass for more)
worse with every future addition.

Fields: `css_class`/`element_id`/`href` (from the element's own
`attributes.class`/`.id`/`.href`), `placeholder`/`label`/`name`/
`disabled`/`required`/`form` (top-level fields `discover_components.js`
already emitted but nothing downstream read), and
`color`/`background_color`/`font_size`/`font_weight`/`display`/`position`
(a curated subset of `getComputedStyle()`, not the full
`CSSStyleDeclaration` - just enough for a future visual-reconstruction
pass to distinguish "looks like a heading" from "looks like a disabled
button" without re-crawling the site).

**Deliberately excludes `value`**: `discover_components.js` does emit a
live `.value` for inputs/textareas/selects, but a fill's actual value is
already captured by `record_component_interaction` at the moment it's
set - the reliable source, since discovery can run before or after a
fill. Re-reading `.value` into `ComponentFacts` would just be a second,
possibly-stale copy of the same fact.

`spiders.graph_sink._component_facts` (see
`docs/dev/spiders/orchestration/graph_sink/component_facts.md#component_facts`) is the one place a
raw JS-discovered component dict gets mapped onto this dataclass; the
`GraphStore` backend's `FACTS_FIELDS` constant (`database/_duckdb_schema.py`,
mirroring the retired Neo4j backend's own `_FACTS_FIELDS` before it)
derives its SQL/dict field list from `ComponentFacts.__dataclass_fields__`
rather than hand-listing the fifteen names a second time, so the schema,
dataclass, and in-memory dict can't drift apart from each other.

## GraphStore

Interface for the crawl graph's persistence/query backend.

Every method is scoped by `site` (the crawled domain) so multiple sites
can be tracked side by side without their data mixing - the tool is
expected to crawl many different websites over time, each analyzed
independently. `url` values passed in and returned are always the
already-normalized, scheme-stripped node key (see `utils.urls.clean_url`)
- the store itself does not re-normalize.

## upsert_page

Create or update a page node for `site`.

A bare rediscovery (`status="Pending"`) must never clobber an already
Finished page's recorded status/components, mirroring the old
`_add_route` behavior - only a non-Pending status overwrites.

`description`: a short page-level summary (meta description, or heading
+ first paragraph - see `page_extraction.run_extraction`'s `description`
extraction), stored so it survives past the crawling process that
discovered it. Empty string never overwrites a previously-recorded
non-empty value, same "don't clobber with less information" discipline
as `context`/`label` above. Retrieved in bulk via `get_page_descriptions`,
not per-page, since synthesis reads every page's description once at the
end of a run.

`title`: the page's own `<title>` (`PageState.title`, already extracted
by `page_extraction.run_extraction` but previously never persisted) -
distinct from `label` (the anchor text of whichever link happened to
lead here, which is absent for the crawl's own start URL and can vary
per discovering page) and from `description` (a sentence-length summary,
not a short name). This is what a document renderer should show as "the
name of this page" - see `get_page_titles`. Same
empty-string-never-clobbers discipline as every other optional field
here.

## get_page_titles

`{url: title}` for every page of `site` that has one recorded (pages
with no/empty title are omitted, not included as `""`) - mirrors
`get_page_descriptions` exactly, for the same reason: a document
renderer reads every page's title once in bulk, not one query per page.

## record_link

Record that a link from `from_url` to `to_url` was discovered, with its
visible text.

Distinct from `record_edge` (an actually-taken navigation): this
captures every discovered link association per source page, so a later
navigation's component description can be verified against the specific
page it claims to have come from. A single page can be linked to from
many different source pages with different anchor text - collapsing
that into one label per destination page (rather than one per from/to
pair) previously caused a navigation's reported component to describe a
link that exists on some other page entirely, not the page actually
being navigated from.

## clear_site

Delete every page/edge/link/component tracked for `site`, leaving other
sites untouched.

For a backend that persists across runs (`DuckDBGraphStore`), this is
what actually resets state between crawls - `Engine.from_config` calls it by default
(`PragmaConfig.fresh`) before wiring the crawl. Without it, a site whose
URLs are per-session tokens (e.g. a `/o/<random-id>` order flow) silently
accumulates a "visited" node for every past run's session, forever - none
of which will ever be seen again, but all of which the next run's
synthesis step still reads back as real history. A process-local store
(`InMemoryGraphStore`) never persists across runs regardless, so this is
a no-op there - implemented uniformly anyway so callers stay
backend-agnostic.

## component-level-frontier

A Page node tracks whether a page was ever visited; the methods below
track the finer-grained question of whether an individual interactive
element on that page was ever acted on. Without this, a component's
"have I touched this" state either lives only in the calling process's
memory (lost the moment the crawler moves on, and never present at all
on turn one of a later run against the same persisted site) or isn't
tracked at all. `page_url` here is always the already-`clean_url`-
canonicalized page key, exactly like every `url` elsewhere in this
interface; `path` is the CSS selector the crawler itself produces for
the element (its `gp()` helper), reused as-is rather than inventing a
second identity scheme.

## record_component

Create or refresh a Component node for `site`/`page_url`/`path`.

Idempotent, same discipline as `upsert_page`: descriptive fields
(tag/text/role/input_type/visible/layer/x/y/width/height/component_type)
refresh on every call since they can legitimately change page to page
(e.g. text, or a layout shift moving an element) - but `interacted`, its
interaction history, and `options` (see `record_component_options`) are
never touched here - only their own dedicated setters do, and a
rediscovery must never clobber state that isn't recomputed every call.

`x`/`y`/`width`/`height` are the element's viewport-relative bounding box
in CSS pixels at the moment it was discovered (see `Crawl4AICrawler`'s
discovery JS), `None` when unknown. This is what makes the stored
checklist a *precise* map of the page - not just "this exists somewhere"
but "this exists right here."

`component_type` is a short, deterministic classification (see
`generators.component_classifier.classify_component_type`) - e.g.
"checkbox," "text field (email)," "combobox (searchable dropdown)" -
computed from tag/role/input_type alone, safe to recompute and overwrite
every call like the other descriptive fields.

`facts` (added 2026-08-11, default `None` -> treated as a blank
`ComponentFacts()`) carries the DOM-attribute/computed-style fields - see
`#ComponentFacts` above. Same idempotent-refresh discipline as every
other descriptive param here, not the interaction-ledger fields.

## record_component_options

Set (fully overwrite) the JSON-encoded `options` field on a Component
node - structured facts beyond simple existence: a revealed dropdown's
choices and which one is selected, a stepper's paired
increment/decrement paths and current value, or a radio/checkbox group's
sibling members. See `component_classifier.py` for what actually
computes these; this method only persists whatever JSON string it's
given, keyed the same way as `record_component`.

Deliberately a *separate* method from `record_component`, not one more
parameter on it: `options` is really only knowable at specific moments
(e.g. right after a click reveals a dropdown's items - a before/after
diff, not something present in any single discovery snapshot), unlike
every field `record_component` refreshes, which is recomputable from the
current DOM alone on every single call. Folding `options` into that same
call would mean every ordinary rediscovery (most of which have no idea
what a component's options are) would overwrite it back to empty,
permanently erasing something more expensive to learn than to lose.

Auto-creates the Component node if it doesn't already exist, mirroring
`record_component_interaction`'s auto-create (a caller with options to
record for a path it hasn't explicitly `record_component`-ed yet should
still succeed, not silently no-op).

`option_labels` (2026-08-12) is `options`' clean, human-readable
projection - the same `["Mi Gusto (selected)", "Solo Empanadas", ...]`
shape `component_tree.py`'s generated document already rendered, now
also stored directly on the node so reading it doesn't require
generating (or re-parsing) that document. `GraphStoreSink` computes it
via `component_classifier.format_option_choices(component_classifier.
describe_options(options))` right before every `record_component_
options` call - this method itself does no parsing of `options`, it
only persists whatever it's handed, same "storage does no business
logic" discipline `ComponentFacts`/`ComponentFamily` already established.
`None`/omitted stores `[]`.

## record_component_interaction

Mark a component as interacted with and append one interaction record.

Auto-creates the Component node if it doesn't already exist (mirrors
`record_edge`'s auto-create of its endpoint Page nodes) - an interaction
can be recorded even if `record_component` wasn't called first in some
code path.

`source_path` (added 2026-08-11, default `""`): set by
`GraphStoreSink.record_interaction` when `path` is a consolidated
dropdown/choice-group's representative node rather than the specific
member that actually acted (see
`docs/dev/spiders/orchestration/graph_sink/sink.md#_resolve_write_path`) - both backends
embed it into the interaction entry only when non-empty, so an ordinary
(ungrouped) interaction's JSON shape is byte-for-byte unchanged from
before this field existed.

## record_component_network

Append one JSON-encoded batch of meaningful network requests
(`spiders/content/network_filter.py::filter_meaningful_requests`'s output
for one interaction) to a Component's `network_requests` list - same
append-only-list-of-JSON-strings shape as
`record_component_interaction`'s `interactions`, not an overwrite like
`record_component_options`' `options`: an interaction can only happen
once per path today (the tracker's consult-before-act guard forbids
re-interacting an already-interacted path), but modeling this as append
is safe-by-construction if that invariant ever changes, rather than
silently losing an earlier batch. Auto-creates the Component node if
missing, same discipline as
`record_component_interaction`/`record_component_options`.

## get_component_states

All known components for one page: `{path: {tag, text, interacted,
visible, x, y, width, height, component_type, options, ...every
ComponentFacts field}}`.

One query per page visit, not one per component -
`GraphStoreInteractionTracker` (`spiders/orchestration/graph_sink.py`) is the
caller. `x`/`y`/`width`/`height` are `None` for components recorded
before position tracking existed, or by a test double that doesn't
report it. `options` is the raw JSON string set by
`record_component_options`, `""` if never set - callers that need the
structured value should `json.loads` it themselves.

## count_unexplored_components

`(unexplored_count, total_count)` of components tracked across all of
`site`.

`semantic_only=True` excludes `layer="pointer"` components (the
cursor:pointer catch-all, capped and noisier than the semantic/ARIA
selector) from both counts.

## get_component_ledger

`{page_url: {path: {tag, text, interacted, interactions, x, y, width,
height, component_type, options, network_requests, ...every
ComponentFacts field}}}` for all of `site`.
`network_requests` is a list of `filter_meaningful_requests`-shaped dicts
(already-decoded, not raw JSON strings) - `[]` if the component never
triggered a meaningful request or predates this field's existence. The
`ComponentFacts` fields are `""`/`False` for a component recorded before
this field set existed, or auto-created via the interaction/options/
network ghost-node path without ever going through `record_component`'s
own `facts` param.

The durable, human-inspectable "what did I do on this page, and to
what" record, sourced from real persisted state - what
`GraphPRDSynthesizer` reads to build its component catalog.

## component-families

`apply_tag_labels`/`record_component_families`/`get_component_families`
are a post-hoc, whole-site pass over already-discovered components (see
`generators/component_family.py`), not part of the live per-page
crawl write path - `Engine._apply_component_families` calls all three
once, after a crawl finishes.

`apply_tag_labels` (and the `component_family.py` helpers that fed it,
`tags_with_multiple_instances`/`label_for_tag`) used to live here too: a
Neo4j-Browser-specific visual affordance (node color follows label) with
no equivalent once nothing renders the graph visually. Removed along
with that backend.

## record_component_families / get_component_families

A from-scratch rebuild every call - `record_component_families` clears
any families a previous run wrote for `site` before writing the new
set, since cluster membership isn't guaranteed to stay the same between
runs as the underlying components change (a component that was a
singleton last run might gain a sibling this run, or vice versa).
`get_component_families` is the read side, used by tests and available
for a future PRD-narration pass to consume (not wired in yet -
deliberately deferred, see the module's own commit history).

## record_inferred_requests / get_inferred_requests

Same "post-hoc, whole-site pass, full rebuild every call" contract as
`record_component_families`/`get_component_families`, one layer over:
`generators/request_family.py` groups network requests already
captured on Component nodes into distinct `InferredRequest` endpoints
(see that module's own docstring for the algorithm), and `Engine.
_apply_request_graph` (`core/engine.py`) is what calls both this
build step and these two `GraphStore` methods, once per crawl, right
after `_apply_component_families`.

## static-text-content

A separate node kind from Component, deliberately: Component carries an
entire interaction-tracking surface (interacted/interactions/options/
network_requests, plus every frontier/tracker query that filters by it)
that non-interactive text has no use for. Folding text into Component
means either every text node permanently carries meaningless blank
fields (the exact "ghost node" smell the Phase 0 ghost-node bug fix
exists to eliminate) or every interaction-frontier query needs a `kind
!= 'text'` filter bolted on. A second, purpose-built node kind with its
own identity keeps the interaction surface untouched by construction.

## record_text_content

Create or refresh a text-content record - idempotent upsert, same
discipline as `record_component`'s descriptive fields, but with no
interaction state to preserve (none exists for non-interactive text).
Called once per page visit (see `docs/dev/spiders/orchestration/page_visitor/visitor.md#visit`),
*not* re-called on same-page reveals the way `record_inventory` now is
for `Component` - text revealed only by an interaction is a real,
structurally-symmetric gap to the ghost-node bug, but out of scope for
this feature by explicit design.
