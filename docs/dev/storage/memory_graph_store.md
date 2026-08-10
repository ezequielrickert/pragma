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
