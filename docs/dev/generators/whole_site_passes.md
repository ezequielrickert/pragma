# `src/generators/whole_site_passes.py`

## module

The two post-hoc passes that enrich a finished crawl's graph, reading it
whole and writing back into it.

Both used to live in `src/core/engine.py`. They moved when the
stop/resume work pushed that file past 500 lines and an SRP read found
the seam: these are pure graph-in/graph-out post-processing that touch no
`Engine` state whatsoever, and they change for different reasons than the
crawl wiring that used to surround them.

What makes them "whole-site" rather than part of the live crawl is that
neither has an incremental mode. Family clustering has to compare every
component the crawl found against every other, and endpoint inference has
to see every captured request at once — unlike everything `GraphStoreSink`
writes page by page as the crawl happens. They run once, after
`crawl_site` returns and before `GraphPRDSynthesizer` reads the graph.

A session that stopped early skips both by default, along with the rest
of synthesis — see `core/engine.md#_should_synthesize`.

## _flatten_ledger

Flattens `get_component_ledger`'s `{page_url: {path: {...}}}` nesting
into the flat list of dicts every pass here expects, with `page_url` and
`path` folded into each record.

The ledger's per-page nesting exists for `GraphPRDSynthesizer`'s
page-by-page narration; a whole-site pass wants the opposite shape. Both
passes below needed exactly this and had their own identical copy of it
inline, which is what this replaces.

## apply_component_families

Infers reusable component families, gives each a one-sentence
LLM-narrated purpose, and adds per-tag Neo4j labels.

Four steps, always in this order:

1. Read every discovered component and flatten it.
2. `build_component_families` clusters them — `purpose` is still `""` on
   every family at this point, since clustering never calls the model.
3. `narrate_family_purposes` fills in `purpose`, one `agent.generate()`
   call per family that has any member text at all.
4. The narrated families are written via `record_component_families` (a
   full rebuild of the site's family structure every call, per that
   method's contract), and `tags_with_multiple_instances` picks which raw
   HTML tags appear often enough to earn their own Neo4j label.

## apply_request_graph

Infers distinct API endpoints, and which components trigger each one,
from the network requests already captured on Component nodes.

Reads the graph a second time rather than sharing the previous pass's
already-flattened list. That is deliberate: it keeps the two passes fully
separable — one is about component *look-alikes*, this one about
*endpoint* identity — at the cost of one extra `get_component_ledger`
read per crawl. A single local read, once per whole crawl, not a hot
path.
