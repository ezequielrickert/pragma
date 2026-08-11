# `src/storage/memory_graph_store.py`

## module

Reproduces the exact dict-based tracking Pragma used before Neo4j
support was added (one flat routes/edges pair per site instead of one
shared pair), so runs and tests without a live Neo4j instance behave
identically to before.

## _FACTS_FIELDS

`ComponentFacts.__dataclass_fields__` (`docs/dev/core/interfaces.md#ComponentFacts`)
keys, in declaration order - added 2026-08-11 so `_new_component_record`,
`get_component_states`, and `get_component_ledger` all project the same
fifteen field names off one list rather than three independently
hand-typed copies, mirroring the Neo4j backend's own `_FACTS_FIELDS`
(`docs/dev/storage/neo4j_graph_store.md#_FACTS_FIELDS--_COMPONENT_DESCRIPTIVE_SET--_COMPONENT_FACTS_RETURN`).

## _new_component_record

A fresh default record for a path first touched via
`record_component_interaction`/`record_component_options` rather than
`record_component` - a plain dict literal, not a shared class-level
default, since `interactions` is a mutable list every record needs its
own instance of, not one aliased across every auto-created path. Blanks
every `ComponentFacts` field too (`**asdict(ComponentFacts())`), same
"blank, not absent" ghost-node discipline as the Neo4j backend's
`_component_blank_stub`.

## record_component

`facts` (2026-08-11, default `None` -> `ComponentFacts()`) is spread into
the stored record via `**asdict(facts or ComponentFacts())` - the
descriptive fields refresh on every call, same discipline as
tag/text/role/etc., while `interacted`/`interactions`/`options`/
`network_requests` are explicitly carried over from `existing` since
those are never `record_component`'s to overwrite.

## record_component_interaction

`source_path` (2026-08-11) follows the same conditional-inclusion rule
as the Neo4j backend (docs/dev/storage/neo4j_graph_store.md#record_component_interaction)
- present in the appended interaction dict only when non-empty, so both
backends' `interactions` entries stay identically shaped for the same
call.
