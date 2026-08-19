"""The API-contract write/read path for `LadybugGraphStore` - storage-
migration plan step 7. `_LadybugNetworkMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)`/`self._ensure_page(...)` existing on whatever it ends
up mixed into, same as every other mixin in this package.

Replaces `database/ladybug/deferred.py`'s five network-related
placeholders (`record_page_network`, `record_component_network`,
`get_page_network_ledger`, `record_inferred_requests`,
`get_inferred_requests`) with the real thing, and retires
`generators/request_family.py`'s whole-site rebuild pass entirely: an
`Endpoint`'s aggregates (status codes, schemas, auth schemes, callers)
are never stored, only computed on read from the `Request` nodes that
prove them (`get_inferred_requests` below) - there is nothing here that
can go stale between crawl passes the way a rebuilt `inferred_requests`
table could.

One request, one `conn.execute()` call - not batched via `UNWIND` the way
`record_components`/`record_text_contents` are. Those exist because a
single discovery pass can produce hundreds of components; a page's own
network traffic or one interaction's fallout is a handful of requests at
most (148 first-party observations across an entire site crawl in the
snapshot the storage plan measured), and a `Request`'s optional
`Payload` attachment (0, 1, or 2 bodies) varies per row in a way an
`UNWIND` batch can't express without an unverified conditional-`CREATE`
Cypher construct - a plain per-row loop is simpler and, at this volume,
not a real cost.

Details: docs/dev/database/ladybug/network.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import InferredRequest
from utils.urls import is_opaque_token
from ._cypher import set_clause
from .clock import now
from .ids import endpoint_id as _endpoint_id

_REQUEST_FIELDS = (
    "method", "path", "query_params", "resource_type", "status", "status_text",
    "failed", "failure_text", "request_schema", "response_schema",
    "latency_ms", "media_type", "auth_scheme", "observed_at",
)
_REQUEST_SET_CLAUSE = set_clause("req", _REQUEST_FIELDS)

_ENDPOINT_ON_CREATE = (
    "e.method = $method, e.host = $host, e.path_pattern = $path_pattern, "
    "e.path_params = $path_params, e.first_party = $first_party, e.call_count = 0"
)


def _shortest(excerpts: Any) -> str:
    """One body out of every observation of it, or `""` for none.

    Shortest first, ties broken lexicographically. Any observation is as
    valid an example as any other, so this exists to be *deterministic* -
    two runs over the same graph must produce the same document - and
    shortest keeps a 8KB-truncated blob from becoming the example when a
    small one was also seen.
    Details: docs/dev/database/ladybug/network.md#_shortest
    """
    return min(excerpts, key=lambda body: (len(body), body)) if excerpts else ""


def _pattern_and_params(path: str) -> Tuple[str, List[str]]:
    """`("/orders/{id}/items", ["id"])` for `"/orders/8d206b72.../items"` -
    the same opaque-segment heuristic `route_shape` applies to page URLs
    and the retired `request_family.normalized_endpoint` applied to API
    URLs, applied here at write time instead of in a post-hoc rebuild
    pass. Two dynamic segments both read `{id}` in the pattern itself
    (an endpoint's shape does not need them told apart to be the same
    endpoint); `path_params` disambiguates positionally (`["id",
    "id_2"]`) for anything that wants the count without re-parsing the
    pattern string.
    Details: docs/dev/database/ladybug/network.md#_pattern_and_params
    """
    segments = [seg for seg in path.split("/") if seg]
    params: List[str] = []
    shaped: List[str] = []
    for segment in segments:
        if is_opaque_token(segment):
            name = "id" if not params else f"id_{len(params) + 1}"
            params.append(name)
            shaped.append(f"{{{name}}}")
        else:
            shaped.append(segment)
    return "/" + "/".join(shaped), params


def _merge_shape(accumulated: str, incoming: str) -> str:
    """Union of two JSON-encoded shapes, marking keys that aren't in
    both `"?"` - moved from the retired `request_family.py` verbatim
    (that module's own docstring has the full reasoning); this is the
    only surviving caller.
    Details: docs/dev/database/ladybug/network.md#_merge_shape
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


def _request_params(item: Dict[str, Any], first_party: bool) -> Dict[str, Any]:
    """One request dict (`network_filter.filter_meaningful_requests` shape,
    plus `GraphStoreSink`'s own `is_first_party` stamp) into every param
    `_write_request`/`_write_third_party_hit` below need - built once so
    the two write paths agree on what an "endpoint" is.
    Details: docs/dev/database/ladybug/network.md#_request_params
    """
    method = (item.get("method") or "").upper()
    host = item.get("host", "")
    path = item.get("path", "")
    path_pattern, path_params = _pattern_and_params(path)
    return {
        "method": method, "path": path, "query_params": list(item.get("query_params") or []),
        "resource_type": item.get("resource_type", ""), "status": item.get("status"),
        "status_text": item.get("status_text", ""), "failed": bool(item.get("failed", False)),
        "failure_text": item.get("failure_text") or "",
        "request_schema": item.get("body_shape", ""), "response_schema": item.get("response_shape", ""),
        "latency_ms": item.get("latency_ms"), "media_type": item.get("media_type", ""),
        "auth_scheme": item.get("auth_scheme", ""), "observed_at": now(),
        "host": host, "path_pattern": path_pattern, "path_params": path_params,
        "endpoint_id": _endpoint_id(method, host, path_pattern), "first_party": first_party,
        "request_body_hash": item.get("request_body_hash") or "",
        "request_body_excerpt": item.get("request_body_excerpt") or "",
        "request_body_length": item.get("request_body_length") or 0,
        "response_body_hash": item.get("response_body_hash") or "",
        "response_body_excerpt": item.get("response_body_excerpt") or "",
        "response_body_length": item.get("response_body_length") or 0,
    }


def _payload_clauses(params: Dict[str, Any]) -> str:
    """`WITH req MERGE (:Payload)... CREATE (req)-[:HAS_BODY]->...` for
    whichever of `request_body_hash`/`response_body_hash` are non-empty -
    0, 1, or 2 bodies per request, which is exactly the per-row variability
    that keeps this write path off `UNWIND` (see module docstring).
    Details: docs/dev/database/ladybug/network.md#_payload_clauses
    """
    clauses = []
    if params["request_body_hash"]:
        clauses.append(
            """
            WITH req
            MERGE (rp:Payload {hash: $request_body_hash})
            ON CREATE SET rp.byte_length = $request_body_length, rp.content = $request_body_excerpt
            CREATE (req)-[:HAS_BODY {direction: 'request'}]->(rp)
            """
        )
    if params["response_body_hash"]:
        clauses.append(
            """
            WITH req
            MERGE (sp:Payload {hash: $response_body_hash})
            ON CREATE SET sp.byte_length = $response_body_length, sp.content = $response_body_excerpt
            CREATE (req)-[:HAS_BODY {direction: 'response'}]->(sp)
            """
        )
    return "".join(clauses)


class _LadybugNetworkMixin:
    """Details: docs/dev/database/ladybug/network.md#_ladybugnetworkmixin"""

    def record_page_network(self, page_url: str, requests: List[Dict[str, Any]]) -> None:
        """Requests a page's own load fired, with no component to blame -
        the `LOADED` half of the `Request`/`Endpoint` split.
        Details: docs/dev/database/ladybug/network.md#record_page_network
        """
        if not requests:
            return

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            for item in requests:
                if item.get("is_first_party", True):
                    params = _request_params(item, first_party=True)
                    conn.execute(
                        f"""
                        MATCH (page:Page {{url: $page_url}})
                        CREATE (req:Request)
                        SET {_REQUEST_SET_CLAUSE}
                        CREATE (page)-[:LOADED]->(req)
                        MERGE (e:Endpoint {{id: $endpoint_id}})
                        ON CREATE SET {_ENDPOINT_ON_CREATE}
                        SET e.call_count = e.call_count + 1
                        CREATE (req)-[:CALLS]->(e)
                        {_payload_clauses(params)}
                        """,
                        {**params, "page_url": page_url},
                    )
                else:
                    self._merge_third_party_endpoint(conn, item)

        self._call(op)

    def record_component_network(self, page_url: str, path: str, requests: List[Dict[str, Any]]) -> None:
        """Requests one interaction fired - the `TRIGGERED` half. Each
        request must carry the `visit_id`/`step_seq` `GraphStoreSink`
        stamps onto it (from the same `VisitStep` the matching
        `record_component_interaction` call used): that pair is what
        finds the exact `Interaction` node to hang this `Request` off of,
        not just "some interaction on this component". A request missing
        either is skipped - it names no interaction to attribute to.
        Details: docs/dev/database/ladybug/network.md#record_component_network
        """
        if not requests:
            return
        component_id = f"{page_url}|{path}"

        def op(conn) -> None:
            for item in requests:
                if not item.get("is_first_party", True):
                    self._merge_third_party_endpoint(conn, item)
                    continue
                visit_id, step_seq = item.get("visit_id"), item.get("step_seq")
                if not visit_id or not step_seq:
                    continue
                params = _request_params(item, first_party=True)
                conn.execute(
                    f"""
                    MATCH (c:Component {{id: $component_id}})-[:PERFORMED]->
                          (i:Interaction {{visit_id: $visit_id, step_seq: $step_seq}})
                    CREATE (req:Request)
                    SET {_REQUEST_SET_CLAUSE}
                    CREATE (i)-[:TRIGGERED]->(req)
                    MERGE (e:Endpoint {{id: $endpoint_id}})
                    ON CREATE SET {_ENDPOINT_ON_CREATE}
                    SET e.call_count = e.call_count + 1
                    CREATE (req)-[:CALLS]->(e)
                    {_payload_clauses(params)}
                    """,
                    {**params, "component_id": component_id, "visit_id": visit_id, "step_seq": step_seq},
                )

        self._call(op)

    def _merge_third_party_endpoint(self, conn, item: Dict[str, Any]) -> None:
        """A tracker/ads/analytics call: bump `Endpoint.call_count`,
        create no `Request` at all - per-observation fidelity for traffic
        this application doesn't own is noise, not signal (96% of
        captured requests in the snapshot that shaped this plan were
        exactly this kind of call).
        Details: docs/dev/database/ladybug/network.md#_merge_third_party_endpoint
        """
        params = _request_params(item, first_party=False)
        conn.execute(
            f"""
            MERGE (e:Endpoint {{id: $endpoint_id}})
            ON CREATE SET {_ENDPOINT_ON_CREATE}
            SET e.call_count = e.call_count + 1
            """,
            params,
        )

    def get_inferred_requests(self) -> List[InferredRequest]:
        """Every first-party endpoint's contract, computed from the
        `Request`s that prove it - `endpoints_discovered`/`openapi.py`'s
        parity shim for the retired `request_family.build_inferred_requests`
        rebuild pass. Third-party endpoints (`first_party = false`) are
        deliberately excluded: this method answers "what is this
        application's own API", not "what does it integrate with" - see
        `Endpoint`'s own schema comment for the asymmetric retention this
        reflects.
        Details: docs/dev/database/ladybug/network.md#get_inferred_requests
        """
        def op(conn) -> List[InferredRequest]:
            rows = conn.execute(
                """
                MATCH (r:Request)-[:CALLS]->(e:Endpoint {first_party: true})
                OPTIONAL MATCH (page:Page)-[:LOADED]->(r)
                OPTIONAL MATCH (i:Interaction)-[:TRIGGERED]->(r)
                OPTIONAL MATCH (comp:Component)-[:PERFORMED]->(i)
                OPTIONAL MATCH (comp_page:Page)-[:HAS_COMPONENT]->(comp)
                OPTIONAL MATCH (r)-[:HAS_BODY {direction: 'request'}]->(sent:Payload)
                OPTIONAL MATCH (r)-[:HAS_BODY {direction: 'response'}]->(received:Payload)
                RETURN e.id, e.method, e.host, e.path_pattern,
                       r.query_params, r.request_schema, r.response_schema, r.status,
                       r.latency_ms, r.auth_scheme, r.media_type,
                       page.url, comp_page.url, comp.path,
                       sent.content, received.content
                """
            )
            buckets: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                (endpoint_id_value, method, host, path_pattern, query_params, request_schema,
                 response_schema, status, latency_ms, auth_scheme, media_type,
                 loaded_page, comp_page_url, comp_path, sent_body, received_body) = row
                bucket = buckets.setdefault(
                    endpoint_id_value,
                    {
                        "method": method, "endpoint": f"{host}{path_pattern}",
                        "query_params": set(), "request_schema": "", "response_schema": "",
                        "triggered_by": set(), "loaded_by": set(),
                        "status_codes": set(), "latencies_ms": [],
                        "auth_schemes": set(), "media_types": set(),
                        "request_examples": set(), "response_examples": set(),
                    },
                )
                bucket["query_params"].update(query_params or [])
                bucket["request_schema"] = _merge_shape(bucket["request_schema"], request_schema or "")
                bucket["response_schema"] = _merge_shape(bucket["response_schema"], response_schema or "")
                if isinstance(status, int):
                    bucket["status_codes"].add(status)
                if isinstance(latency_ms, int):
                    bucket["latencies_ms"].append(latency_ms)
                if auth_scheme:
                    bucket["auth_schemes"].add(auth_scheme)
                if media_type:
                    bucket["media_types"].add(media_type)
                if loaded_page:
                    bucket["loaded_by"].add(loaded_page)
                if comp_page_url and comp_path:
                    bucket["triggered_by"].add((comp_page_url, comp_path))
                if sent_body:
                    bucket["request_examples"].add(sent_body)
                # Only a successful call's body describes the happy path: a
                # 422's body is the error shape, and publishing it as the
                # endpoint's response example would misdescribe the API.
                if received_body and isinstance(status, int) and 200 <= status < 300:
                    bucket["response_examples"].add(received_body)

            return [
                InferredRequest(
                    method=data["method"], endpoint=data["endpoint"],
                    query_params=tuple(sorted(data["query_params"])),
                    body_shape=data["request_schema"], response_shape=data["response_schema"],
                    triggered_by=tuple(sorted(data["triggered_by"])),
                    loaded_by=tuple(sorted(data["loaded_by"])),
                    status_codes=tuple(sorted(data["status_codes"])),
                    latencies_ms=tuple(sorted(data["latencies_ms"])),
                    auth_schemes=tuple(sorted(data["auth_schemes"])),
                    media_types=tuple(sorted(data["media_types"])),
                    request_example=_shortest(data["request_examples"]),
                    response_example=_shortest(data["response_examples"]),
                )
                for _, data in sorted(buckets.items())
            ]

        return self._call(op)
