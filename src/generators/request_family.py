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

from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qsl, urlsplit

from ..core.interfaces import InferredRequest
from ..utils.urls import is_opaque_token


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


def build_inferred_requests(components: List[Dict[str, Any]]) -> List[InferredRequest]:
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

    Returns:
        One `InferredRequest` per distinct `(method, endpoint,
        query_param_names)` group, sorted by that same key for a
        deterministic order:
        - `body_shape`/`response_shape`: the first non-empty shape seen
          across every request in the group - a known, accepted
          simplification (not a merge/union of every occurrence's shape)
          when different calls to the same endpoint carry slightly
          different payloads; documented here rather than silently
          assumed.
        - `triggered_by`: every distinct `(page_url, path)` whose
          component fired at least one request in this group, sorted.
    """
    buckets: Dict[Tuple[str, str, Tuple[str, ...]], Dict[str, Any]] = {}
    for comp in components:
        page_url = comp.get("page_url")
        path = comp.get("path")
        if not page_url or not path:
            continue
        for req in comp.get("network_requests") or []:
            method = (req.get("method") or "").upper()
            url = req.get("url") or ""
            if not method or not url:
                continue
            key = (method, normalized_endpoint(url), query_param_names(url))
            bucket = buckets.setdefault(
                key, {"body_shape": "", "response_shape": "", "triggered_by": set()}
            )
            bucket["triggered_by"].add((page_url, path))
            if not bucket["body_shape"] and req.get("body_shape"):
                bucket["body_shape"] = req["body_shape"]
            if not bucket["response_shape"] and req.get("response_shape"):
                bucket["response_shape"] = req["response_shape"]

    return [
        InferredRequest(
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            body_shape=data["body_shape"],
            response_shape=data["response_shape"],
            triggered_by=tuple(sorted(data["triggered_by"])),
        )
        for (method, endpoint, query_params), data in sorted(buckets.items())
    ]
