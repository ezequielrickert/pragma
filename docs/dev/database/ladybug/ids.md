# database/ladybug/ids.py

## module

Composite primary keys for the node tables that need them.

**Why composite keys rather than a surrogate id plus an index.** Ladybug (like
Kùzu, which it derives from) hash-indexes the **primary key only**. There are no
secondary indexes, so any property a write path upserts on has to *be* the key
or every upsert becomes a table scan. `Component`, `Container` and `TextContent`
are all upserted by `(page_url, path)` and never by either half alone, so that
pair is the key.

Built in exactly one place so every write and every read agree on its shape - a
key assembled inline in two modules is a key that eventually differs in one of
them.

**`path` here is a CSS selector**, not a URL path -
`body > header > div:nth-of-type(2) > a`, from `discover_components.js`'s
`gp()`. Worth stating because `Request.path` in the same package *is* a URL
path, and the two are easy to conflate when reading a query.

## component_id

`page_url|path`.

`|` is safe as a separator because neither a CSS selector nor a `route_shape`d
URL contains one, and it is preferred over a hash because a component's id
stays **legible in a raw query result**. Debugging a graph where every key is a
digest is materially worse, and `raw()`/`schema_card()` exist precisely so
people read query output directly.

## split_component_id

The inverse. Only traversal results need it - a fresh write already has
`page_url` and `path` as separate arguments - which is why it is used by
`semantic.py::_provenance_by_node` (working back from a matched `Component`)
and not by any writer.

Callers that need the page half of an id should use this rather than splitting
on `|` themselves: this is the one function that knows what the separator is.

## endpoint_id

`method` plus the endpoint's `host/path_pattern` - the contract's identity, not
an observation's. Two calls to `POST /orders` share one `Endpoint` and remain
two `Request` nodes, which is the whole first-party retention model in one key.
