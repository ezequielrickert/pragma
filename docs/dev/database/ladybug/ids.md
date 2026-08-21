# database/ladybug/ids.py

## module

Primary keys for the node tables that need one built rather than supplied by
the caller.

**Why composite/content keys rather than a surrogate id plus an index.**
Ladybug (like Kùzu, which it derives from) hash-indexes the **primary key
only**. There are no secondary indexes, so any property a write path upserts
on has to *be* the key or every upsert becomes a table scan.

`Component` and `Container` are content-derived and page-decoupled since the
canonical-schema migration (issue #134): two instances discovered on
different pages `MERGE` onto the same row the moment every field that stays
on the node matches exactly - the ordinary primary-key `MERGE` this database
already does for `Page`/`Site`, applied here to a key built from content
instead of from where a write happened to originate.

Built in exactly one place so every write agrees on its shape - a key
assembled inline in two modules is a key that eventually differs in one of
them.

## component_content_id

A hash of every field named by `schema.py`'s `DESCRIPTIVE_COMPONENT_FIELDS`,
in that fixed order - exactly the set of fields that stay on `Component`
after #134 (`path`/`element_id`/geometry moved to `HAS_COMPONENT`). A field
absent from the given dict reads as `""`, the same "absence is itself a
shared trait" rule the leaf feature vector (#131) uses for the same reason.

## container_content_id

Same scheme as `component_content_id`, over `CONTAINER_DESCRIPTIVE_FIELDS`
(`tag`, `role`, `landmark`, `css_class` - everything that stays on
`Container` after #134).

## endpoint_id

`method` plus the endpoint's `host/path_pattern` - the contract's identity, not
an observation's. Two calls to `POST /orders` share one `Endpoint` and remain
two `Request` nodes, which is the whole first-party retention model in one key.
