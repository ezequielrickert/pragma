# `spiders/content/network_filter.py`

## module

Pure, deterministic reduction of crawl4ai's raw network-capture event
stream to the subset worth attributing to a component interaction. No
browser/I/O dependency - kept separate from `crawl4ai_crawler.py` so it's
directly unit-testable against hand-built event dicts, mirroring
`component_classifier.py`'s own "pure functions, no I/O" placement.

Event shapes below are copied from reading crawl4ai's own source
(`async_crawler_strategy.py`'s `handle_request_capture`/
`handle_response_capture`/`handle_request_failed_capture`), not assumed:

- `{"event_type": "request", "url", "method", "headers", "post_data",
  "resource_type", "is_navigation_request", "timestamp"}`
- `{"event_type": "response", "url", "status", "status_text", "headers",
  "from_service_worker", "request_timing", "timestamp",
  "body": {"text": <full response body text>}}` - note `body.text` is
  populated on every successful capture, not just on error.
- `{"event_type": "response_capture_error", "url", "error", "timestamp"}` -
  the response event's own body-reading step failed (e.g. a streamed/binary
  body `response.text()` can't decode) - no `status` available for this URL.
- `{"event_type": "request_failed", "url", "method", "resource_type",
  "failure_text", "timestamp"}`
- `*_capture_error` variants for the request/request_failed handlers too,
  carrying no resource_type - never matches the xhr/fetch keep-filter below,
  so they're silently excluded rather than needing special-casing.

## _MEANINGFUL_RESOURCE_TYPES

resource_type values worth attributing to "what did clicking this actually
call" - not images/fonts/stylesheets/documents/websockets, which are noise
for a component-level request-info question.

## _json_shape / _shape_of_json_text

`_json_shape` reduces a parsed JSON value to its structural shape - key
names and value **types** only, e.g. `{"share_token": "abc123"}` becomes
`{"share_token": "string"}`. `_shape_of_json_text` wraps it end to end
(`json.loads` -> `_json_shape` -> `json.dumps`, `""` for empty/non-JSON
input) so the real parsed value only ever exists inside that one function
call - it's never held onto, returned, or logged anywhere else.

## filter_meaningful_requests

Reduce one `arun()` call's `result.network_requests` (or `None`) to the
meaningful subset, one dict per kept request: `{"method", "url",
"resource_type", "status": Optional[int], "failed": bool, "failure_text":
Optional[str], "body_shape": str, "response_shape": str}`.

**Update (2026-08-12) - request/response body text is now read, but only
ever as an input to `_shape_of_json_text`, never as output:** this
function's original design deliberately never read body text at all -
"it can be arbitrarily large ... and may contain secrets/PII", and
dropping it here meant it never reached `GraphStore`. That reasoning
still holds for the real *text* - it's exactly as true today. What
changed is the introduction of `_shape_of_json_text`, which makes it
possible to extract something useful (the JSON's *shape* - field names,
value types) **without ever letting the real values survive past the
computation** - `post_data`/`body.text` are read from the raw event,
passed straight into `_shape_of_json_text`, and only that function's
already-scrubbed return value (a JSON string with type names, never
values) becomes part of the output. A non-JSON body (HTML, binary, plain
text) produces `""` - there's no shape to describe, and the raw text is
discarded exactly as before. See `tests/test_network_filter.py::
test_shape_of_json_text_real_secret_value_never_survives` for the actual
regression test pinning this guarantee.

**Known limitation**: request/response/failure are joined purely by URL,
not by any per-request id crawl4ai doesn't expose - two requests to the
identical URL within one interaction (e.g. a retry) can have their
status/failure (and now `body_shape`/`response_shape`) misattributed to
the wrong attempt (last-one-wins, since later events overwrite earlier
ones in the lookup dicts below). Accepted for this feature's purposes,
not fixed here.


## _is_meaningful

Replaces the old flat `resource_type in {"xhr","fetch"}` check, because
that set silently excluded the single most important request an old
application makes.

A classic `<form method="post">` submit navigates the page, and Playwright
reports a navigation as resource_type **`document`**, not xhr/fetch. A
server-rendered legacy system - the case this whole project exists for -
sends its data that way, so the API contract inferred from such a site
came out empty, and nothing said why: the coverage report counts pages and
components, not request kinds.

The method is what separates the two `document` cases. A GET document is
someone following a link, and every crawled page produces one; keeping
those would bury the real endpoints under one entry per page. A non-GET
document is a form submitting data, which is exactly an API call that
happens to answer with a page instead of JSON.

Consequence worth expecting: those requests have `body_shape: ""`, since a
form submit sends `application/x-www-form-urlencoded`, not JSON, and
`_shape_of_json_text` returns `""` for anything it cannot parse. The
method, endpoint, and status still describe the operation - which is more
than the previous behaviour, where it did not exist at all.

## _latency_ms

crawl4ai already stamps every captured event with `timestamp`
(`async_crawler_strategy.py`), so latency is the gap between a request and
its response - no new capture, just two fields that were being discarded.

Reported as `None`, never `0`, when no response arrived: a failed request
has a send time and nothing else, and `0 ms` would read as
"instantaneous" rather than "never answered".

**What this number is and is not.** It is measured through the crawl's own
browser, which runs with `light_mode`, `memory_saving_mode` and blocked
images. It is a *relative* signal - this endpoint takes ten times longer
than that one - and feeds the Nielsen "visibility of system status" rule.
It is not a performance measurement of the application.

Inherits an existing limitation rather than introducing one: every map in
`filter_meaningful_requests` is keyed by url, so two requests to the same
url within one batch overwrite each other. That was already true of
`status`.

## _auth_scheme

crawl4ai captures request headers on every event, and this module threw
them away wholesale - the same situation `timestamp` was in before the
latency work. Reading them is what turns "no security schemes, by design"
into a real `securitySchemes` block.

**Names, never values.** For `Authorization`, only the scheme word is
kept: `Bearer eyJhbGci...` becomes `"bearer"`. A scheme name is not a
secret; the token after it is, and it never leaves this function. An
API-key-looking header contributes its *name* (`header:x-api-key`), and a
`Cookie` header contributes only the fact that one was present. This is
the same names-not-values discipline `query_param_names` has always
followed, applied to a second place the same secrets could have leaked
from.

Tested by asserting the credential is absent from the output, not merely
that the scheme is present - a test that only checks the good case would
pass on an implementation that leaked.

## _media_type

The response's `content-type`, charset stripped. Without it the API
contract assumed `application/json` for everything, so an endpoint
answering XML or a redirect was described wrongly rather than vaguely.

## _split_url

`(host, path, query_param_names)` - the redaction policy applied **at capture
time**, not left for a later pass to enforce.

A live query string is exactly the per-instance data this feature never
persists: an order id, a share token. Only a parameter's *name* survives, sorted
and deduplicated so the same endpoint reports the same list regardless of the
original call's param order.
