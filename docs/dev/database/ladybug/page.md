# database/ladybug/page.py

## module

The navigation-graph half of the observation tier: `Page`, `LINKS_TO`,
`NAVIGATES_TO`.

`_ensure_page` lives here rather than in `store.py` because this is the mixin
that owns `upsert_page`'s full contract. `component.py` and `text_content.py`
reach it as `self._ensure_page(...)`, resolved through the MRO instead of a
direct import - the same pattern the retired DuckDB backend's mixins used, and
the reason those modules do not import each other.

Two columns went away with the migration and are worth naming so nobody
re-adds them: `context` had zero readers anywhere, and `label` had zero
writers - including its own dedicated `get_page_label`, which itself had zero
callers.

## _ladybugpagemixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`. It is also the
mixin the others depend on: `component.py` and `text_content.py` reach
`_ensure_page` through the MRO, so this class has to be in the bases of any
store that uses them.

## _ensure_page

Creates a bare `Pending` page when one does not exist, called by every method
that references a page without owning the full `upsert_page` contract for it -
links, edges, components, text content.

This is what makes write order not matter. A component recorded for a page the
crawl has not formally arrived at yet still lands, instead of being dropped by
a `MATCH` that finds nothing.

## upsert_page

Create or update a page node. **Never clobbers `Finished` with `Pending`**,
which is the whole reason this is not a plain `SET`: a later write that only
knows a page exists must not undo the record of it having been completed, or a
resumed crawl would re-walk what it already finished.

## record_page_metadata

A page's `<meta>` tags as one `MAP` property rather than a child table. They
are read whole with the page and never traversed, which is this schema's rule
for property-versus-node.

## record_link

A link discovered in the markup, with its visible text - **distinct from a
navigation actually taken**. `LINKS_TO` is what the site claims you can reach;
`NAVIGATES_TO` is what the crawl proved. Collapsing them would make an
unvisited link indistinguishable from a walked transition.

## record_links

One `UNWIND` for a whole discovery pass instead of a round-trip per link.
`record_components` set the precedent: a pass's worth of writes is worth one
trip through the single writer thread.

## record_edge

A successful navigation, idempotent per `(from, to, component, action)`. Seeing
the same transition again bumps `observation_count` rather than adding a second
edge, so an edge's weight is how often it was observed and not how many times
the crawl was restarted.

`first_seen_run` is written once and never overwritten - the same
"first sighting is permanent" rule `_touch_site`'s `first_crawled` follows.

## is_visited

Whether a page has *concluded* - `Finished` or `Failed` - and should not be
queued again. `Failed` counts: a page that could not be visited is not a page
to retry forever, and `UrlFrontier.requeue`'s own cap is the other half of
that decision.

## get_pending

Up to `limit` `Pending` urls, sorted, unbounded when `limit` is `None`. The
frontier's resume source: these pages *are* a cut-short run's saved progress,
which is why `PragmaConfig.fresh` defaults to off.

## get_scouted

Up to `limit` `"Scouted"` page urls
(`docs/dev/spiders/orchestration/graph_sink/sink.md#scouted_page_status`),
sorted ascending, unbounded if `limit` is `None` - same contract as
`get_pending`, mirrored directly after it in the source. Read by
`MechanicalCrawler._scouted_urls`
(`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_scouted_urls`)
to resume `pragma dynamic` (`interact_only`) from a separate `pragma
static` (`scout_only`) run's output once its scout sweep has fully
drained.

## get_progress_table_rows

Every page as `{url, status, components}`, unfinished first then by url, so a
reader sees what is outstanding before what is done.

## get_page_descriptions

`{url: description}` for pages that have one. Pages without are absent rather
than mapped to `""` - the same "missing key beats empty string" choice
`get_component_regions` makes.

## get_page_titles

`{url: title}`, same shape and same omission rule.

## count_visited

`(finished, total)`, **excluding `External` pages**. A page the crawl only ever
saw a link to was never something it owed a visit, so counting it would make
coverage look worse than it is - and coverage is the number every other
document is caveated by.

## get_edges

Every `NAVIGATES_TO` edge with its observation count and run provenance, in
first-seen order. The input to `build_mermaid_graph`,
`user_flows.build_flow_graph` and `analysis/graph_projection.py` - three
consumers, one read, which is why it is memoized in `CachingGraphStore`.
