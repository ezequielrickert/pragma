# `src/generators/request_family.py`

## module

Pure, deterministic grouping of network requests already captured on
Component nodes into distinct API endpoints - "how many *different*
endpoints does this site actually call, and which components call each
one", not just "did this button trigger a network call" (which
`network_requests` on a Component already answers). Same problem shape
as `component_family.py`, one level up: many raw facts, one reusable
identity underneath.

**Verified against real data (empanad.app)**: 9 distinct endpoints
correctly identified - 5 `GET`s (orders/flavors/participants/selections),
3 `POST`s, 1 `DELETE` - with the right components attributed to each
(4 different "Agregar" buttons all correctly merged into one
`participant_selections` endpoint instead of 4 separate facts).

## normalized_endpoint

`host/path` with opaque generated path segments collapsed to `{id}` -
reuses `utils.urls.is_opaque_token`, the exact heuristic `route_shape`
already applies to page URLs, for the analogous reason: a dynamic id in
an API path is the same kind of per-instance noise a page's own session
token is. Query string is dropped entirely here (see
`query_param_names`) - it's a separate identity dimension, not folded
into the same string, so two endpoints differing only by *which* query
params they carry aren't accidentally treated as identical or as
completely unrelated based on how their query strings happen to be
formatted.

## query_param_names

Sorted, deduplicated query-string parameter **names** only - e.g.
`("order_id", "select")` for `?select=*&order_id=eq.<uuid>` - the value
side (`eq.<uuid>`) is dropped entirely. This is the actual privacy
boundary for query strings: an order id or share token in a query value
is exactly the kind of per-instance data this feature, and the
`network_filter.py` shape-computation it pairs with, deliberately never
persists.

## build_inferred_requests

Buckets by `(method, normalized_endpoint, query_param_names)` - the
three-part identity a distinct endpoint is defined by. Within a bucket
(all requests that are "the same endpoint"):
- `body_shape`/`response_shape` are the first non-empty shape seen
  across the group - a documented simplification, not a merge/union of
  every occurrence (two calls to the same endpoint with slightly
  different payload shapes only ever show the first one seen). Accepted
  the same way `component_family.py` accepts single-linkage clustering's
  chaining risk: a known, stated tradeoff, not a silent gap.
- `triggered_by` collects every distinct `(page_url, path)` that fired at
  least one request in the group - so a single endpoint hit by several
  different components lists all of them, not just one.

Result is sorted by the bucket key for a deterministic order regardless
of input order.
