# `database/ladybug/page.py`

## module

**Scope note**: this file's `Details:` comments reference many anchors
in this doc (`#_ladybugpagemixin`, `#upsert_page`, `#get_pending`, etc.)
that don't exist yet - no `docs/dev/database/ladybug/` mirror existed
for any file in this package before `get_scouted` below was added, only
a stale doc for a since-removed backend
(`docs/dev/database/memory_graph_store.md`). Backfilling the rest of
this package's docs is a separate, much larger task than the
`two_phase_crawl` feature that needed this one method documented - out
of scope here, not silently skipped.

## get_scouted

Up to `limit` `"Scouted"` page urls
(`docs/dev/spiders/orchestration/graph_sink/sink.md#scouted_page_status`),
sorted ascending, unbounded if `limit` is `None` - same contract as
`get_pending`, mirrored directly after it in the source. Read by
`MechanicalCrawler._scouted_urls`
(`docs/dev/spiders/orchestration/mechanical_loop/loop.md#_scouted_urls`)
to seed phase 2's frontier once a `two_phase_crawl` run's scout sweep
has fully drained.
