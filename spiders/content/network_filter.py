"""Pure reduction of crawl4ai's raw network events to the ones worth keeping.
Details: docs/dev/spiders/content/network_filter.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Asynchronous API traffic - the obvious case.
# Details: docs/dev/spiders/content/network_filter.md#_meaningful_resource_types
_ASYNC_RESOURCE_TYPES = {"xhr", "fetch"}

# A classic <form method="post"> that navigates the page is resource_type
# "document", not xhr/fetch - and a server-rendered legacy application, the
# whole point of this project, submits data that way.
# Details: docs/dev/spiders/content/network_filter.md#_is_meaningful
_NAVIGATION_RESOURCE_TYPE = "document"


# Request headers whose mere presence identifies an authentication scheme.
# Only the *name* is ever kept, and for `authorization` only the scheme
# word - never a credential.
# Details: docs/dev/spiders/content/network_filter.md#_auth_scheme
_API_KEY_HEADER_HINTS = ("api-key", "apikey", "x-auth", "auth-token", "access-token", "x-token")


def _auth_scheme(headers: Dict[str, str]) -> str:
    """The authentication scheme a request used, from header names alone.

    Args:
        headers: the request's headers, as crawl4ai captured them.

    Returns:
        `"bearer"`/`"basic"`/... - the first word of an `Authorization`
        header, lowercased, which is a scheme name and never a secret. Or
        the *name* of an API-key-looking header (`"header:x-api-key"`), or
        `"cookie"` when the request carried one. `""` when nothing
        suggests authentication.

        Values are never read. A bearer token, a basic credential and a
        session cookie all stay entirely out of the graph - the same
        names-not-values discipline `query_param_names` already follows.
    Details: docs/dev/spiders/content/network_filter.md#_auth_scheme
    """
    lowered = {name.lower(): value for name, value in (headers or {}).items()}
    authorization = lowered.get("authorization", "")
    if authorization:
        scheme = authorization.split(" ", 1)[0].strip().lower()
        return scheme or "authorization"
    for name in lowered:
        if any(hint in name for hint in _API_KEY_HEADER_HINTS):
            return f"header:{name}"
    return "cookie" if "cookie" in lowered else ""


def _media_type(headers: Dict[str, str]) -> str:
    """The response's media type, without charset. `""` when unstated."""
    for name, value in (headers or {}).items():
        if name.lower() == "content-type":
            return (value or "").split(";")[0].strip().lower()
    return ""


def _is_meaningful(event: Dict[str, Any]) -> bool:
    """Whether one `request` event describes a call worth documenting.

    Args:
        event: one raw crawl4ai network event with `event_type == "request"`.

    Returns:
        `True` for any `xhr`/`fetch` request, and for a `document` request
        whose method isn't GET - see
        `docs/dev/spiders/content/network_filter.md#_is_meaningful` for why
        plain page navigations stay excluded while form submits don't.
    """
    resource_type = event.get("resource_type")
    if resource_type in _ASYNC_RESOURCE_TYPES:
        return True
    if resource_type != _NAVIGATION_RESOURCE_TYPE:
        return False
    # The method is what separates the two document cases, not crawl4ai's
    # `is_navigation_request` flag: that is true for a link click and a form
    # submit alike, so it cannot tell them apart.
    # Details: docs/dev/spiders/content/network_filter.md#_is_meaningful
    return (event.get("method") or "").upper() != "GET"


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
    Details: docs/dev/spiders/content/network_filter.md#filter_meaningful_requests
    """
    if not raw_events:
        return []

    statuses_by_url: Dict[str, Optional[int]] = {}
    status_text_by_url: Dict[str, str] = {}
    media_type_by_url: Dict[str, str] = {}
    auth_scheme_by_url: Dict[str, str] = {}
    failures_by_url: Dict[str, str] = {}
    response_body_by_url: Dict[str, str] = {}
    post_data_by_url: Dict[str, str] = {}
    sent_at_by_url: Dict[str, float] = {}
    received_at_by_url: Dict[str, float] = {}
    for event in raw_events:
        event_type = event.get("event_type")
        if event_type == "response":
            url = event.get("url")
            statuses_by_url[url] = event.get("status")
            status_text_by_url[url] = event.get("status_text") or ""
            media_type_by_url[url] = _media_type(event.get("headers") or {})
            _remember_timestamp(received_at_by_url, event)
            body_text = (event.get("body") or {}).get("text")
            if body_text:
                response_body_by_url[url] = body_text
        elif event_type == "response_capture_error":
            # Body unreadable but the response did arrive - no status either way.
            statuses_by_url.setdefault(event.get("url"), None)
            _remember_timestamp(received_at_by_url, event)
        elif event_type == "request_failed":
            failures_by_url[event.get("url")] = event.get("failure_text") or "request failed"
        elif event_type == "request":
            _remember_timestamp(sent_at_by_url, event)
            scheme = _auth_scheme(event.get("headers") or {})
            if scheme:
                auth_scheme_by_url[event.get("url")] = scheme
            post_data = event.get("post_data")
            if post_data:
                post_data_by_url[event.get("url")] = post_data

    results = []
    for event in raw_events:
        if event.get("event_type") != "request":
            continue
        if not _is_meaningful(event):
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
                "latency_ms": _latency_ms(sent_at_by_url.get(url), received_at_by_url.get(url)),
                "status_text": status_text_by_url.get(url, ""),
                "media_type": media_type_by_url.get(url, ""),
                "auth_scheme": auth_scheme_by_url.get(url, ""),
            }
        )
    return results


def _remember_timestamp(into: Dict[str, float], event: Dict[str, Any]) -> None:
    """Record one event's `timestamp` under its url, if it has both."""
    timestamp = event.get("timestamp")
    url = event.get("url")
    if url and isinstance(timestamp, (int, float)):
        into[url] = float(timestamp)


def _latency_ms(sent_at: Optional[float], received_at: Optional[float]) -> Optional[int]:
    """Whole milliseconds between a request and its response.
    Details: docs/dev/spiders/content/network_filter.md#_latency_ms
    """
    if sent_at is None or received_at is None or received_at < sent_at:
        return None
    return round((received_at - sent_at) * 1000)
