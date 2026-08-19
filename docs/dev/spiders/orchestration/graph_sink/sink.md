# `spiders/orchestration/graph_sink/sink.py`

## module

Phase 3 of the crawl4ai migration: live `GraphStore` wiring for
`MechanicalCrawler` - `DuckDBGraphStore` (or `InMemoryGraphStore`) becomes
the crawl's source of truth, written to as the crawl happens rather than
batched by an in-process orchestrator afterward.

The detail-rich writer `MechanicalCrawler` calls directly at each point
in the crawl (page arrival, full component/link inventory, each
interaction, navigation edges, page completion) - `tracker.py`'s
`GraphStoreInteractionTracker` is the separate, thin read-cache
`InteractionTracker` seam, kept in its own file since it has its own
reason to change.

`GraphStoreSink` also owns `_representative_for`: a per-page
`{member_path: representative_path}` map built by `record_inventory`
whenever it collapses a dropdown/menu/radio/checkbox group into one
`Component` node, and consulted by `record_interaction`/
`record_component_network` to redirect a later write on any of that
group's members onto the same node instead of creating a new one. See
`record_inventory`/`_record_choice_group`/`_resolve_write_path` below.

## GraphStoreSink

Writes a `MechanicalCrawler` crawl's facts into `GraphStore` as they
happen. Every method maps to one point in the crawl where a hook's
result is ready to persist - invoked from `MechanicalCrawler`'s own
Python-side orchestration (not a crawl4ai hook itself) since it needs the
actual interaction *result* (did the URL change), which only exists once
`crawler.click()`/`fill()` returns.

## _write

Runs one blocking `GraphStore` write off the event loop via
`asyncio.to_thread` - `GraphStore` backends are synchronous
(`DuckDBGraphStore` in particular blocks on its single writer thread), so
calling `fn` directly here would stall every other crawl worker sharing
this event loop for the duration.

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

## record_page_metadata

The page's own `<meta>` tags, extracted on every navigation. `None`/empty
metadata is a no-op write, not an empty-dict overwrite - a page whose
extraction genuinely found nothing leaves whatever (if anything) an
earlier visit already recorded untouched.

## record_page_network

Requests the page's own load fired, with no component to blame - not
attributable to any one interaction, but part of the page's own network
contract all the same (e.g. the API calls a SPA needs just to render at
all). Only called once, right after discovery - not on the
post-interaction path, where `record_component_network` below attributes
requests to the specific component that triggered them instead.

## record_text_content

Full, unconditional static-text inventory - called once per page visit
(see `docs/dev/spiders/orchestration/page_visitor/visitor.md#visit`), not
re-called on same-page reveals the way `record_inventory` now is for
`Component` (see `GraphStore.record_text_content`'s docstring for why
that's a deliberate, documented cut rather than an oversight).

## record_inventory

Full, unconditional component + link inventory for one discovery pass -
every *ungrouped* component gets a `record_component` call (idempotent,
safe to call again on rediscovery) regardless of whether anything on it
changed. Detected steppers get their structured facts attached via
`record_component_options`, reusing `component_classifier.py` unchanged.

A *grouped* component - a member of `group_choice_sets` (radio/checkbox
sharing a `name`) or `group_option_families` (a dropdown/menu's
`role="option"`-family siblings) - never gets its own `record_component`
call at all. Instead `_record_choice_group` writes exactly one
representative node per group (real tag/text/component_type, not a blank
stub - see `_component_args`) carrying the whole group's choices as one
`options` JSON blob. This is a deliberate node-count reduction: a
5-choice dropdown produces 1 `Component` node instead of 5 near-identical
ones. See `component_classifier.md#group_option_families` for why
`role="tab"` is excluded from this collapse.

## _component_args

One component's descriptive fields, as `record_component(s)` kwargs, or
`None` if it has no path (nothing to write). Factored out so the main
inventory loop and `_record_choice_group`'s representative write go
through the exact same code - a group's representative node gets real
fields the same way an ordinary ungrouped component does, never a
blank-stub ghost-node shape.

Also passes `facts=component_facts(comp)` (see
`docs/dev/spiders/orchestration/graph_sink/component_facts.md#component_facts`)
- a group's representative gets the *representative member's own*
attributes/style, same as its tag/text/component_type; the other
members' facts are not separately recorded (they never had their own
`Component` node to begin with, same as their tag/text).

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
request (see `spiders/content/network_filter.py`) - the "request
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
`docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`)
- an interrupted pass leaves the page genuinely incomplete, so it must
stay `Pending` for its guaranteed follow-up pass, not be marked
`Finished` prematurely.

## failed_page_status

`FAILED_PAGE_STATUS = "Failed"` - a page `UrlFrontier.requeue`
(`docs/dev/spiders/orchestration/mechanical_loop/frontier.md#requeue`)
gave up on after `max_requeue_attempts` interrupted passes: reliably
anti-bot-blocked, or a redirect destination too many independent passes
kept landing on and requeuing. Distinct from `Pending` (`get_pending()`
excludes it, so a resumed run doesn't retry it forever) and from
`Finished` (coverage/measurement passes correctly treat it as never
actually analyzed, not silently done). `GraphStore.is_visited` treats it
the same as `Finished` - both mean "concluded, don't queue or visit
again" - see `DuckDBGraphStore.is_visited`'s own comment.

## record_page_failed

Called once by `_worker` (`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_worker-give-up`)
when `UrlFrontier.requeue` refuses to requeue a page again - the
concluding write for a page that gave up, the same role
`record_page_finished` plays for one that actually finished.

## scouted_page_status

`SCOUTED_PAGE_STATUS = "Scouted"` - a `scout_only` run (`pragma static`'s
own crawl mode,
`docs/dev/spiders/orchestration/mechanical_loop/config.md#scout_only`)
has finished discovery + sink bookkeeping for this page but not yet
interaction. Distinct from `Pending` (still owed a first pass of any
kind) and `Finished` (`interact()`'s own trailing `record_page_finished`
call overwrites this once a later, separate `interact_only` pass -
`pragma dynamic`'s own resume mode - actually runs the page's
interaction frontier). `is_visited()` deliberately does not treat
`Scouted` as
concluded - unlike `Failed`/`Finished` above, a scouted page is real,
unfinished work still owed to the crawl.

## record_page_scouted

Called once `PageVisitor.scout()`'s discovery + bookkeeping pass
completes for a page
(`docs/dev/spiders/orchestration/page_visitor/visitor.md#scout`) - never
interrupted the way `interact()` can be (`scout()` never clicks, so
nothing can trigger a mid-pass navigation), so this call is
unconditional, unlike `record_page_finished`'s own
not-`interrupted_by_navigation` guard. Mirrors `record_page_finished`'s
own shape/params (`page_key`, `component_count`).

## _mark_party

Stamps `is_first_party` onto each already-filtered request dict, so the storage
layer can route a call to `Request`+`Endpoint` or to `Endpoint` alone without
re-deriving the host comparison. See
`docs/dev/database/ladybug/network.md#_merge_third_party_endpoint` for the
asymmetric retention this feeds.

## base_url

The same two values `UrlFrontier` gates on, so a link is judged in-scope
identically whether it is being queued or recorded.

`None` disables the check, preserving the pre-scope behaviour for callers that
never pass it - tests, mostly.

## external_page_status

The status for a link target the frontier will never visit because it points off
the crawled domain.

Without it those pages sit in `Pending` forever: the frontier refuses them on
scope grounds while this sink records them anyway, so `get_pending` returns work
that can never be done and `count_visited` can never reach 100% on any site that
links outward.

## link-target-key

A link target is keyed by `route_shape`, not `clean_url`.

Every other page key in the graph is shaped - `visit()` derives `page_key` that
way - so recording a link target unshaped would mint a second node for a screen
that already has a canonical one, which is exactly what `route_shape` exists to
prevent.

## off-site-targets

Marked **after** `record_links`, never instead of it.

The edge to an off-site page is real data - where this site sends you - and stays
recorded. Only the target's status changes, so it stops posing as work the crawl
still owes.

## record_state_styles

Called once per page visit, the same cadence as `record_text_content` and for
the same reason: these come from the page's stylesheets, which a click cannot
change, so recording them per reveal would write identical rows repeatedly.
