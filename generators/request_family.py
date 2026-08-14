"""Pure, deterministic inference of distinct API endpoints - and which
Components trigger each one - from network requests already captured
during a crawl. No I/O, same placement discipline as component_family.py.

What this solves: `network_filter.filter_meaningful_requests` already
reduces crawl4ai's raw event stream to one dict per meaningful (xhr/
fetch) request, and `GraphStoreSink` already stores each Component's own
requests as a list on that Component's node. That's enough to answer "did
this button call an API" but not "how many *distinct* endpoints does this
site actually have, and which components call each one" - the same
request (e.g. a POST to `/participant_selections`) fired by four
different "Agregar" buttons shows up as four separate facts with no
indication they're the same endpoint. This module groups them.

Details: docs/dev/generators/request_family.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from core.interfaces import InferredRequest
from utils.urls import is_opaque_token


def normalized_endpoint(url: str) -> str:
    """`host/path`, with every opaque generated path segment (an order
    id, a session token) collapsed to `{id}` - the query string is
    dropped entirely here (see `query_param_names` for that half).

    Args:
        url: a full request URL, e.g.
            `"https://x.supabase.co/rest/v1/orders/8d206b72-.../items"`.

    Returns:
        e.g. `"x.supabase.co/rest/v1/orders/{id}/items"`. Reuses
        `utils.urls.is_opaque_token` - the exact same "does this look
        like a generated id, not a real word" heuristic `route_shape`
        already applies to page URLs, applied here to API URLs for the
        analogous reason: a dynamic id in an endpoint's path is the same
        kind of per-instance noise a page's own session token is.
    """
    split = urlsplit(url)
    segments = [seg for seg in split.path.split("/") if seg]
    shaped = ["{id}" if is_opaque_token(seg) else seg for seg in segments]
    return split.netloc + "/" + "/".join(shaped)


def query_param_names(url: str) -> Tuple[str, ...]:
    """Sorted, deduplicated query-string parameter *names* from `url` -
    never the values, which can carry the exact per-instance data
    (an order id, a share token) this whole feature deliberately never
    persists.

    Args:
        url: a full request URL.

    Returns:
        e.g. `("order_id", "select")` for
        `"...?select=*&order_id=eq.8d206b72-..."` - sorted so the same
        endpoint always produces the same tuple regardless of the
        original query string's own param order.
    """
    split = urlsplit(url)
    return tuple(sorted({name for name, _ in parse_qsl(split.query)}))


def _merge_shape(accumulated: str, incoming: str) -> str:
    """Union of two JSON-encoded shapes, marking keys that aren't in both.

    Args:
        accumulated: the shape built from earlier samples, or `""`.
        incoming: this sample's shape, or `""`.

    Returns:
        A JSON-encoded object shape holding every key either side had.
        A key missing from one side is suffixed `"?"` (e.g. `"string?"`),
        which is how the OpenAPI generator tells required from optional -
        a key absent from some calls to the same endpoint is optional by
        observation. Non-object shapes (an array, a bare string) can't be
        merged this way, so the first non-empty one wins unchanged.
    Details: docs/dev/generators/request_family.md#_merge_shape
    """
    if not accumulated:
        return incoming
    if not incoming or accumulated == incoming:
        return accumulated
    try:
        left, right = json.loads(accumulated), json.loads(incoming)
    except (json.JSONDecodeError, TypeError):
        return accumulated
    if not isinstance(left, dict) or not isinstance(right, dict):
        return accumulated

    merged: Dict[str, Any] = {}
    for key in sorted(set(left) | set(right)):
        in_both = key in left and key in right
        value = left.get(key, right.get(key))
        merged[key] = value if in_both or not isinstance(value, str) else f"{value}?"
    return json.dumps(merged)


def build_inferred_requests(
    components: List[Dict[str, Any]], page_requests: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> List[InferredRequest]:
    """Group every network request across `components` into one
    `InferredRequest` per distinct `(method, endpoint, query_param_names)`.

    Args:
        components: every component discovered for one site, flattened
            (same shape `component_family.build_component_families`
            takes - see `Engine._apply_component_families`/the analogous
            request-graph orchestrator for the flattening step). Each
            dict needs `"page_url"`, `"path"`, and `"network_requests"`
            (a list of `network_filter.filter_meaningful_requests`-shaped
            dicts - `method`/`url`/`body_shape`/`response_shape`, among
            other fields this function doesn't use). Components with no
            `network_requests` (the common case - most components never
            trigger a network call) contribute nothing and aren't an
            error.
        page_requests: `{page_url: [request, ...]}` for requests each
            page's own *load* fired, from
            `GraphStore.get_page_network_ledger`. Omitted or `None`
            behaves exactly as before this parameter existed - which is
            also what every `InMemoryGraphStore`-backed caller that
            predates it still does.

    Returns:
        One `InferredRequest` per distinct `(method, endpoint,
        query_param_names)` group, sorted by that same key for a
        deterministic order:
        - `body_shape`/`response_shape`: the *union* of every sample's
          shape, with keys absent from some samples marked `"?"` - see
          `_merge_shape`. This replaced "first non-empty shape wins",
          which could not distinguish a required field from an optional
          one and so made every OpenAPI property required by accident.
        - `triggered_by`: every distinct `(page_url, path)` whose
          component fired at least one request in this group, sorted.
        - `loaded_by`: every page whose load fired it, sorted.
        - `status_codes`/`latencies_ms`: every distinct status and every
          measured latency observed, sorted.
    """
    buckets: Dict[Tuple[str, str, Tuple[str, ...]], Dict[str, Any]] = {}

    def absorb(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fold one request into its bucket, returning the bucket (or None
        if the request has no method/url to group by)."""
        method = (req.get("method") or "").upper()
        url = req.get("url") or ""
        if not method or not url:
            return None
        key = (method, normalized_endpoint(url), query_param_names(url))
        bucket = buckets.setdefault(
            key,
            {
                "body_shape": "", "response_shape": "",
                "triggered_by": set(), "loaded_by": set(),
                "status_codes": set(), "latencies_ms": [],
                "auth_schemes": set(), "media_types": set(),
            },
        )
        bucket["body_shape"] = _merge_shape(bucket["body_shape"], req.get("body_shape") or "")
        bucket["response_shape"] = _merge_shape(bucket["response_shape"], req.get("response_shape") or "")
        if isinstance(req.get("status"), int):
            bucket["status_codes"].add(req["status"])
        if isinstance(req.get("latency_ms"), int):
            bucket["latencies_ms"].append(req["latency_ms"])
        if req.get("auth_scheme"):
            bucket["auth_schemes"].add(req["auth_scheme"])
        if req.get("media_type"):
            bucket["media_types"].add(req["media_type"])
        return bucket

    for comp in components:
        page_url = comp.get("page_url")
        path = comp.get("path")
        if not page_url or not path:
            continue
        for req in comp.get("network_requests") or []:
            bucket = absorb(req)
            if bucket is not None:
                bucket["triggered_by"].add((page_url, path))

    for page_url, requests in (page_requests or {}).items():
        for req in requests:
            bucket = absorb(req)
            if bucket is not None:
                bucket["loaded_by"].add(page_url)

    return [
        InferredRequest(
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            body_shape=data["body_shape"],
            response_shape=data["response_shape"],
            triggered_by=tuple(sorted(data["triggered_by"])),
            loaded_by=tuple(sorted(data["loaded_by"])),
            status_codes=tuple(sorted(data["status_codes"])),
            latencies_ms=tuple(sorted(data["latencies_ms"])),
            auth_schemes=tuple(sorted(data["auth_schemes"])),
            media_types=tuple(sorted(data["media_types"])),
        )
        for (method, endpoint, query_params), data in sorted(buckets.items())
    ]
