# `database/memory_graph_store.py`

## module

Reproduces the exact dict-based tracking Pragma used before any live
graph-database support was added (one flat routes/edges pair per site
instead of one shared pair), so runs and tests without a live DuckDB (or,
formerly, Neo4j) instance behave identically to before.

## _FACTS_FIELDS

`ComponentFacts.__dataclass_fields__` (`docs/dev/core/interfaces.md#ComponentFacts`)
keys, in declaration order - added 2026-08-11 so `_new_component_record`,
`get_component_states`, and `get_component_ledger` all project the same
fifteen field names off one list rather than three independently
hand-typed copies, mirroring `DuckDBGraphStore`'s own `FACTS_FIELDS`
(`database/_duckdb_schema.py`) - a role the retired Neo4j backend's own
`_FACTS_FIELDS` played before it.

## _new_component_record

A fresh default record for a path first touched via
`record_component_interaction`/`record_component_options` rather than
`record_component` - a plain dict literal, not a shared class-level
default, since `interactions` is a mutable list every record needs its
own instance of, not one aliased across every auto-created path. Blanks
every `ComponentFacts` field too (`**asdict(ComponentFacts())`), same
"blank, not absent" ghost-node discipline as `DuckDBGraphStore`'s
`_ensure_component_stub` (and the retired Neo4j backend's
`_component_blank_stub` before it).

## record_component

`facts` (2026-08-11, default `None` -> `ComponentFacts()`) is spread into
the stored record via `**asdict(facts or ComponentFacts())` - the
descriptive fields refresh on every call, same discipline as
tag/text/role/etc., while `interacted`/`interactions`/`options`/
`network_requests` are explicitly carried over from `existing` since
those are never `record_component`'s to overwrite.

## record_component_interaction

`source_path` (2026-08-11) follows the same conditional-inclusion rule
as `DuckDBGraphStore` (and, before it, the retired Neo4j backend) -
present in the appended interaction dict only when non-empty, so every
backend's `interactions` entries stay identically shaped for the same
call.

## component_families

`record_component_families`/`get_component_families` store/return
exactly the list they're given/hold - a full replace on every write,
same "no incremental merge" contract `DuckDBGraphStore`'s version uses
(docs/dev/core/interfaces.md#record_component_families--get_component_families).
