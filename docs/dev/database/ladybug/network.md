# database/ladybug/network.py

## module

The API tier: `Request` (one observed HTTP call), `Endpoint` (the contract
behind it), and `Payload` (a content-addressed body).

**An `Endpoint` stores no aggregates.** Status codes, schemas, auth schemes
and callers are computed on read from the `Request` nodes that prove them, so
there is nothing here that can go stale between crawl passes - which is what
retired `generators/request_family.py`'s whole-site rebuild pass. A rebuilt
table has to be re-run after every write to stay true; a read-time
aggregation cannot be wrong.

**First-party and third-party are retained asymmetrically.** A third-party
host gets an `Endpoint` and no `Request` at all: per-observation fidelity for
a call this application does not own is noise. `get_inferred_requests`
answers "what is this application's own API"; `named_queries.integrations()`
answers "what does it integrate with".

One `conn.execute()` per request rather than an `UNWIND` batch. A page's own
network traffic is a handful of requests (148 first-party observations across
an entire site crawl in the snapshot the storage plan measured), and a
request's optional `Payload` attachment varies per row - 0, 1 or 2 bodies - in
a way an `UNWIND` batch cannot express without an unverified
conditional-`CREATE` construct.

## _ladybugnetworkmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## _pattern_and_params

`("/orders/{id}/items", ["id"])` for `/orders/8d206b72.../items` - the same
opaque-segment heuristic `route_shape` applies to page URLs, applied here at
**write** time rather than in a post-hoc rebuild pass, which is what lets
`Endpoint` be the stored identity.

Two dynamic segments both read `{id}` in the pattern, because an endpoint's
shape does not need them told apart to be the same endpoint. `path_params`
disambiguates positionally (`["id", "id_2"]`) for anything that wants the count
without re-parsing the pattern string.

## _request_params

One request dict - `network_filter.filter_meaningful_requests`' shape plus
`GraphStoreSink`'s `is_first_party` stamp - into every parameter the two write
paths need. Built once so they cannot disagree about what an endpoint is.

## _payload_clauses

The `MERGE (:Payload) ... CREATE (req)-[:HAS_BODY]->` fragment for whichever of
the two body hashes is non-empty.

**This is the per-row variability that keeps this write path off `UNWIND`.** A
request carries 0, 1 or 2 bodies, and an `UNWIND` batch cannot express a
conditional `CREATE` without a construct nobody here has verified against the
engine. At this volume - 148 first-party observations across a whole site crawl
in the snapshot that shaped the plan - a per-row loop is not a real cost.

## _merge_shape

Union of two JSON-encoded shapes, marking keys absent from either `"?"`. Moved
verbatim from the retired `request_family.py`, and this is now its only caller.

Merging on read rather than storing a merged shape is what keeps an endpoint's
contract from going stale: a new observation with an extra optional key widens
the shape the next time it is asked for, with nothing to rebuild.

## _merge_third_party_endpoint

A tracker, ads or analytics call: bump `Endpoint.call_count` and create **no
`Request` at all**.

The asymmetry is deliberate and load-bearing for storage size - 96% of captured
requests in the snapshot that shaped this plan were exactly this kind of call.
Per-observation fidelity for traffic the application does not own is noise, and
keeping the count means `named_queries.integrations()` can still rank vendors by
volume.

## _shortest

Picks one body out of every observation of it.

Shortest first, ties broken lexicographically. Any observation is as valid an
example as any other, so this exists to be **deterministic** - two runs over
the same graph must produce the same document - and "shortest" additionally
keeps an 8KB-truncated blob from becoming the example when a small body was
also seen. It is not a claim that the chosen body is representative, and
`InferredRequest.request_example` says so.

## record_page_network

Requests fired by a page's own load: `Page-[:LOADED]->Request`. No component
is involved, and that distinction is kept rather than folded into a blank
component path - "this endpoint is called when you open /orders" and "this
endpoint is called when you click Save" are different facts, and a contract
that conflates them is wrong about how the application works.

## record_component_network

Requests fired by an interaction, hung off that `Interaction` node via
`TRIGGERED` rather than pooled onto the `Component`. This is what lets one
control clicked twice keep each click's requests separate, and it is what
`generators/user_flows.py` needed to stop labelling a successful branch with
a failed branch's status.

## get_inferred_requests

Every first-party endpoint's contract, aggregated on read.

**Bodies as examples.** Two `OPTIONAL MATCH`es pull the `Payload` on each
side of the call. Filtering `HAS_BODY` by its `direction` property inside the
pattern is confirmed against the real engine, as is reading it through a
named relationship variable with a `WHERE`; the inline form is used here.

A request-body example is taken from any observation - what the client sent
is valid regardless of how the server answered. A **response**-body example
is taken only from calls that answered 2xx, because a 422's body describes
the error shape and publishing it as the endpoint's response example would
misdescribe the happy path. `tests/test_ladybug_network.py::test_a_response_body_from_a_failed_call_is_not_offered_as_the_example`
pins that.

Every body was redacted and truncated at capture time
(`spiders/content/redaction.py`), before it ever reached this table. Verified
through the whole path rather than by unit test alone: a POST carrying a
password, an api key, an email and a card number, with a JWT and an email in
the response, comes out of `build_openapi_document` with all five redacted and
the non-sensitive `username` preserved.

## get_endpoint_discovery_sequence

`(step_seq, endpoint_id)` for every interaction that triggered a
first-party call, ordered by `step_seq` - the input
`generators/coverage.py::_saturation_curve` walks to compute how many
first-party endpoints were still new at each point in the crawl
(docs/adr/0001's `endpoints.saturation_curve`). Deliberately the crawl's
own discovery order, not sorted by endpoint - the curve's whole point is
showing when new surface stopped appearing, which only means something
against the order the crawl actually made the calls in.

## get_request_evidence

Added for ticket #110 (docs/adr/0017): `evidence-log.jsonl`'s `har:<id>`
rows. `Endpoint` is an `OPTIONAL MATCH`, not the `first_party: true`
filter `get_inferred_requests`/`get_endpoint_discovery_sequence` both
apply - not because a real row without an `Endpoint` exists today
(`record_page_network`/`record_component_network` only ever `CREATE
(req:Request)` inside the first-party branch; a third-party observation
never gets a `Request` node at all), but because this method's own job is
indexing whatever was captured, not encoding today's write-path shape as
a required join.

## get_request_latencies_by_page

Added for ticket #119 (docs/adr/0026): `performance-baseline.json`'s own
per-`template_hash` grouping needs page-level attribution `get_inferred_
requests`'s `latencies_ms` can't give it (that's aggregated across every
observation of one *endpoint*, not one *page*). Two queries combined in
Python rather than a Cypher `UNION` - the one exception would be the only
`UNION` in this file.

## get_page_network_ledger

Per-page request list for the documents that describe a page rather than an
endpoint. Whole-site and zero-argument, so it is memoized in
`CachingGraphStore`.
