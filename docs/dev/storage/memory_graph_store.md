# `src/storage/memory_graph_store.py`

## module

Reproduces the exact dict-based tracking Pragma used before Neo4j
support was added (one flat routes/edges pair per site instead of one
shared pair), so runs and tests without a live Neo4j instance behave
identically to before.

## _new_component_record

A fresh default record for a path first touched via
`record_component_interaction`/`record_component_options` rather than
`record_component` - a plain dict literal, not a shared class-level
default, since `interactions` is a mutable list every record needs its
own instance of, not one aliased across every auto-created path.

## record_component_interaction

`source_path` (2026-08-11) follows the same conditional-inclusion rule
as the Neo4j backend (docs/dev/storage/neo4j_graph_store.md#record_component_interaction)
- present in the appended interaction dict only when non-empty, so both
backends' `interactions` entries stay identically shaped for the same
call.
