# database/ladybug/named_queries.py

## module

The named, parameterized query library, plus the `query(name, **params)`
dispatcher over every read on the store.

**Why a library and not just `raw()`.** Per
`research/rag-over-neo4j-for-future-qa.md`, a local model must never drive a
raw tool call. This is what a model at that tier picks from instead: a known,
bounded set of questions with no way to express an arbitrary write. The
questions here are the ones steps 1-8's own `get_*` methods do not already
answer.

## _ladybugnamedqueriesmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## endpoint_contract

One endpoint's contract - status codes, schemas, auth schemes, media types -
aggregated from every `Request` that `CALLS` it.

Unlike `get_inferred_requests`, which deliberately answers only "what is this
application's own API", this answers "what does *this* endpoint look like" for
whichever id is asked about, first- or third-party alike. A third-party
endpoint has no `Request` observations, so its aggregate lists come back empty
rather than absent - the endpoint exists, the detail does not.

Returns `None` for an id that names no endpoint, rather than an empty dict:
"no such endpoint" and "an endpoint with nothing recorded" are different
answers.

## callers_of

Every `Component` whose interaction reached this endpoint, deduplicated and
sorted. The reverse of `endpoint_contract`: given an endpoint, which controls
in the UI cause it. This is the traversal that makes an API contract
actionable - `POST /orders` matters differently once you know four separate
buttons call it.

## integrations

The third-party inventory: every `Endpoint` the application calls and does not
own, busiest first. The counterpart to `get_inferred_requests`' first-party
filter, and the read `generators/architecture_map.py` renders as "who else
does this talk to".

## flows_from

Every page reachable from a starting page within `max_hops` `NAVIGATES_TO`
steps - a traversal, not a stored aggregate.

**`max_hops` is interpolated into the query text, not bound as a parameter.**
Confirmed against the real engine: a variable-length path's hop bound must be a
literal, and a parameter there is a `Parser exception`. Safe because it is a
Python `int` this method clamps to `[1, 10]` itself, never a caller-supplied
string - the clamp is the guard, and it is why the interpolation is acceptable
rather than an injection.

## components_in

Every `Component` a `Container` holds, direct or nested, via `CONTAINS*`. This
is the read that recovers the full ancestry chain `containment.py`
deliberately does not store as a closure.

## unexplored

A parity shim for `get_pending()` under the named-query surface, so a caller
working from the library does not have to know that this particular question
predates the library and lives elsewhere.

## query

Dispatches to a named read by string name.

**What it refuses**, and why the refusals are the interesting part: a name
starting with `_`, and the names `raw` and `query` themselves. Without the
first two exclusions, the bounded surface would not be bounded - `query("raw",
cypher=...)` would hand a model the exact escape hatch this library exists to
keep it away from, and `query("query", ...)` would recurse.

Every public method on the store that takes no positional-only arguments is
reachable this way, not just the ones this module defines, so the library grows
as the store does without a registration list to maintain.
