# `src/storage/neo4j_request_family_store.py`

## module

Inferred-API-endpoint CRUD for `Neo4jGraphStore` - same file-size-driven
split as `neo4j_component_family_store.py`, mixed into `Neo4jGraphStore`
via multiple inheritance in `neo4j_graph_store.py`.

Graph shape:

```
(:RequestFamily {site, method})
    -[:HAS_REQUEST]-> (:Request {site, method, endpoint, query_params,
                                  body_shape, response_shape})
        <-[:TRIGGERS]- (:Component {..., already exists})
```

Unlike `ComponentFamily` (a real similarity-clustering algorithm, computed
entirely in `component_family.py` before ever reaching storage),
`RequestFamily` grouping is a trivial groupby-by-`method` - "GET" and
"POST" are never the same family by definition, there's no threshold or
similarity score involved. That's why the grouping happens right here in
`record_inferred_requests` (`MERGE`ing one `:RequestFamily` node per
distinct method as it iterates `requests`) instead of being computed
externally the way component families are.

## record_inferred_requests

Full rebuild every call: both `:RequestFamily` and `:Request` nodes for
`site` are `DETACH DELETE`d first, then recreated from `requests`. Same
silent-skip behavior as `neo4j_component_family_store.py`'s
`record_component_families` for a `triggered_by` entry that doesn't
resolve to a real `Component` - the request node is still created, just
without that one `TRIGGERS` edge.

## get_inferred_requests

`OPTIONAL MATCH` (not a plain `MATCH`) for the triggering `Component` -
unlike `get_component_families`, which requires at least one
`HAS_VARIANT` edge to match a family at all, a `Request` node is
returned even with zero known triggers (a request whose component
couldn't be resolved at write time is still a real, meaningful fact
about the site's API surface - dropping it here would silently hide
that). `collect(CASE WHEN c IS NOT NULL THEN [...] END)` relies on
Cypher's `collect()` skipping `null` entries on its own, so a
zero-trigger `Request` correctly comes back with `triggered_by = ()`
rather than `(None,)`.
