# database/ladybug/analysis.py

## module

The derived-graph-metrics tier of the store: `Engine`'s post-crawl
`_apply_graph_projection` pass hands `analysis/graph_projection.py::project_graph`'s
output here, and `get_page_metrics` reads it back for the documents that
describe the site's shape.

Why these are `Page` properties and not their own tables, unlike the
retired DuckDB backend's `page_metrics`/`page_modules`: the design rule
this schema follows is *node when traversed or joined, property when always
read whole with its parent*. Nothing ever traverses to a page's centrality
or asks which pages share a betweenness; it is read with the page, every
time. So both writers are `SET`s against `Page` nodes that already exist,
never inserts.

**What is computed every run and then discarded.**
`GraphProjectionResult` also carries `cycles` - the navigation loops
`project_graph` enumerates - and there is no column for them here and no
table to put them in. `Engine` drops them on the floor. That is a real gap
in D13's coverage rather than an oversight to fix quietly: persisting them
means a new node or rel table, and the alternative (a document recomputing
the whole projection to get at them) would run betweenness twice per run
to print one list.

## _metric_fields

One tuple, two consumers: the `RETURN` clause `get_page_metrics` builds and
the dict it zips each row into. Written once so the two cannot drift - the
same reason `schema.py` derives its DDL from `FACTS_FIELDS` instead of
spelling the column list twice.

The order matters only in that it is *shared*; nothing downstream depends
on which field comes first.

## _ladybuganalysismixin

Combined into the public `LadybugGraphStore` by multiple inheritance, and
relies on `self._call(...)` existing on whatever it is mixed into - the
same contract every other mixin in this package has.

## record_page_metrics

Not the full-table rebuild the retired backend's `DELETE`-then-`INSERT`
was. There is no separate table to clear, so a re-run overwrites properties
on the nodes it matches and leaves every other page alone.

`click_depth`, `betweenness` and `pagerank` are explicitly `CAST` inside
the `UNWIND`. An entire batch whose numeric column is `None` on every row
makes Ladybug infer that column as `STRING` and reject the write, and both
all-`None` batches are ordinary: a site with no root-reachable pages has
`click_depth` `None` everywhere, and a graph too small for betweenness has
`0.0` everywhere. Confirmed against the real engine. This is not specific
to `DOUBLE` - `_cypher.py` documents the first instance found, in the
component and text-content writers.

`tests/test_ladybug_read_path.py::test_record_page_metrics_batch_with_all_none_click_depth`
pins the `INT64` case.

## record_page_modules

The Louvain assignment, written the same way and for the same reason.
`module_label` comes from `graph_projection._module_label` - a deterministic
shared-URL-prefix label, no model call, matching the "clustering is pure"
discipline `component_family.py` follows.

## get_page_metrics

One query, not two. Every value both writers above produce is a property of
the same `Page` row, so "metrics" and "module" are one read rather than a
join - which is also why there is no separate `get_page_modules` here even
though there are two writers.

**A page with no module reads back, it is not skipped.** `module_id` is
`None` and `module_label` is `""` for a page the projection never assigned:
a page with no edges of its own, or a run where the projection never got
that far. The documents reading this need to distinguish "crawled, has no
module" from "never crawled", and dropping the row would collapse the two.
`click_depth` is `None` for a page the root cannot reach, the same
distinction `PageMetrics.click_depth` draws.

**Not memoized in `CachingGraphStore`, on purpose.** It is a whole-site
zero-argument read with two callers, which is exactly that cache's shape,
but `record_page_metrics`/`record_page_modules` write precisely what it
reads - the one condition that cache's safety argument rests on not being
true. It would work today only because `_apply_graph_projection` happens to
run before any document reads it. See that module's own comment.
