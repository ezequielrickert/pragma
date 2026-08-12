"""Pure reduction of crawl4ai's raw network events to the ones worth keeping.
Details: docs/dev/crawlers/network_filter.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# xhr/fetch only - not images/fonts/stylesheets/documents/websockets.
# Details: docs/dev/crawlers/network_filter.md#_meaningful_resource_types
_MEANINGFUL_RESOURCE_TYPES = {"xhr", "fetch"}


def _json_shape(value: Any) -> Any:
    """Structural shape of a parsed JSON value - key names and value
    *types* only, never the actual values. `{"share_token": "abc123"}`
    becomes `{"share_token": "string"}` - this is what lets
    `body_shape`/`response_shape` (below) describe an API's contract
    without ever risking a real secret, session token, or personal data
    reaching `GraphStore`.

    Args:
        value: any already-`json.loads`-parsed Python value (dict, list,
            str, int, float, bool, None, or nested combinations).

    Returns:
        - a `dict` with the same keys, each value replaced by its own
          `_json_shape` (recursive) for a dict input.
        - a one-element list holding the shape of `value[0]` (the first
          element is taken as representative of the whole array - real
          API list responses are near-always homogeneous) for a
          non-empty list, or `[]` for an empty one.
        - one of the literal strings `"null"`, `"boolean"`, `"number"`,
          `"string"` for a JSON primitive.
        - `"unknown"` for anything else (defensive; every value
          `json.loads` can produce is one of the cases above).
    """
    if isinstance(value, dict):
        return {k: _json_shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_shape(value[0])] if value else []
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unknown"


def _shape_of_json_text(text: Optional[str]) -> str:
    """JSON-encoded `_json_shape()` of `text`, computed and immediately
    re-encoded so the real parsed value never survives past this one
    function call.

    Args:
        text: raw request/response body text, or `None`/`""`.

    Returns:
        A JSON string (e.g. `'{"share_token": "string"}'`) if `text` was
        valid JSON, or `""` if `text` is empty or isn't valid JSON at all
        (a non-JSON body - HTML, plain text, a binary payload - has no
        shape to describe; `""` means "not applicable", not "empty
        object").
    """
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ""
    return json.dumps(_json_shape(parsed))


def filter_meaningful_requests(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce one `arun()` call's `result.network_requests` to the meaningful subset.
    Details: docs/dev/crawlers/network_filter.md#filter_meaningful_requests
    """
    if not raw_events:
        return []

    statuses_by_url: Dict[str, Optional[int]] = {}
    failures_by_url: Dict[str, str] = {}
    response_body_by_url: Dict[str, str] = {}
    post_data_by_url: Dict[str, str] = {}
    for event in raw_events:
        event_type = event.get("event_type")
        if event_type == "response":
            url = event.get("url")
            statuses_by_url[url] = event.get("status")
            body_text = (event.get("body") or {}).get("text")
            if body_text:
                response_body_by_url[url] = body_text
        elif event_type == "response_capture_error":
            # Body unreadable but the response did arrive - no status either way.
            statuses_by_url.setdefault(event.get("url"), None)
        elif event_type == "request_failed":
            failures_by_url[event.get("url")] = event.get("failure_text") or "request failed"
        elif event_type == "request":
            post_data = event.get("post_data")
            if post_data:
                post_data_by_url[event.get("url")] = post_data

    results = []
    for event in raw_events:
        if event.get("event_type") != "request":
            continue
        if event.get("resource_type") not in _MEANINGFUL_RESOURCE_TYPES:
            continue
        url = event.get("url")
        failed = url in failures_by_url
        results.append(
            {
                "method": event.get("method", ""),
                "url": url,
                "resource_type": event.get("resource_type", ""),
                "status": statuses_by_url.get(url),
                "failed": failed,
                "failure_text": failures_by_url.get(url) if failed else None,
                "body_shape": _shape_of_json_text(post_data_by_url.get(url)),
                "response_shape": _shape_of_json_text(response_body_by_url.get(url)),
            }
        )
    return results
