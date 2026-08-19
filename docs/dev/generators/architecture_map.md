# generators/architecture_map.py

## module

D13. The document that answers the first question a modernisation asks -
"what is this thing made of" - which nothing in the output answered before.

Everything it reports was already being computed or captured with no reader.
`Engine`'s projection pass writes module, click depth, centrality and
articulation points onto every `Page` on every run, and the crawl records
every third-party endpoint it observes. This is the reader.

Fully deterministic, no model call. Module names come from
`graph_projection._module_label`'s shared-URL-prefix heuristic; naming them
better is a separate, explicitly-impure step if it is ever wanted - the same
split `component_family_narrator.py` draws for component families.

## _max_hosts_listed

A real application talks to a long tail of analytics endpoints and font
CDNs. Listing sixty of them buries the three that matter, so the rest are
summed into one row. The count is still exact; only the per-host breakdown is
truncated.

## modulesummary

`shallowest_depth`/`deepest_depth` are `Optional` because a module can exist
entirely out of reach of the entry point: its pages were discovered as links,
so they are real, but no navigation the crawl walked arrives at them.
Reporting `0` there would claim the module is the front door.

## summarize_modules

**A page with no module is excluded, not pooled.** This table answers "what
parts does the application have", and a page that belongs to no part is not a
part. It is still counted in the depth table below, so nothing goes
unreported - it just is not reported as something it isn't. (Contrast
`graph_prd_synthesizer.group_pages_by_module`, which *does* give those pages
their own section: there the unit is "everything to narrate", so leaving them
out would drop them from the document entirely.)

The module's "front door" is its shallowest page, ties broken by url so the
choice is stable across runs. `click_depth is None` sorts last inside that
key, so an unreachable page is never picked as a front door while a reachable
one exists.

## hosts_by_traffic

`integrations()` returns one row per third-party *endpoint*; a reader thinks
in vendors. "Which services does this depend on" is asked per host, so the
rows are summed per host, and the endpoint count is kept alongside because
"one endpoint, 400 calls" and "twelve endpoints, 400 calls" are different
kinds of dependency.

A row with no host becomes `(unknown host)` rather than being dropped: an
endpoint that was observed and cannot be attributed is still a dependency,
and silently losing it would make the totals lie.

## architecturemapdocument

Registered as `architecture`, and in the default `documents` list right after
`coverage` - it is the orientation document, so it comes before the prose
that assumes you know the shape.

Three empty states, each stating which of the possible causes are open rather
than rendering an empty table:

- **No pages at all**: says there is no structure to describe, and emits no
  section headers.
- **Pages but no modules**: either the projection never ran, or the pages
  link too sparsely to cluster - a crawl cut short after a handful of pages
  looks exactly like this. The depth table still renders.
- **No third-party traffic**: stated explicitly, because for a crawl that
  did reach real pages it is a genuine finding (the application calls only
  its own API), not a gap.

The closing section names what the document cannot show: `project_graph`
enumerates navigation cycles every run and nothing persists them. They are
left absent rather than recomputed here - recomputing would run betweenness a
second time per run to print one list. See
`docs/dev/database/ladybug/analysis.md`.
