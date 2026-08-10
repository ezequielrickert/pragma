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

## filter_meaningful_requests

Reduce one `arun()` call's `result.network_requests` (or `None`) to the
meaningful subset, one dict per kept request: `{"method", "url",
"resource_type", "status": Optional[int], "failed": bool, "failure_text":
Optional[str]}`.

Response BODY TEXT is deliberately never read into the output - it can be
arbitrarily large (a full JSON payload, or an entire document for a
misclassified request) and may contain secrets/PII; this function has no
use for it (only request shape - method/url/resource_type/status/failure -
is meaningful for a tree-renderer feature) and dropping it here means it
never reaches `GraphStore`, not just that nothing happens to read it back.

**Known limitation**: request/response/failure are joined purely by URL,
not by any per-request id crawl4ai doesn't expose - two requests to the
identical URL within one interaction (e.g. a retry) can have their
status/failure misattributed to the wrong attempt (last-one-wins, since
later events overwrite earlier ones in the lookup dicts below). Accepted
for this feature's purposes, not fixed here.
