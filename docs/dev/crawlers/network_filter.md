# `src/crawlers/network_filter.py`

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
