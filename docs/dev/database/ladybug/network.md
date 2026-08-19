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

## get_page_network_ledger

Per-page request list for the documents that describe a page rather than an
endpoint. Whole-site and zero-argument, so it is memoized in
`CachingGraphStore`.
