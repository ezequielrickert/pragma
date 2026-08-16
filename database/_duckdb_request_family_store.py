"""Inferred-API-endpoint CRUD for `DuckDBGraphStore` - mirrors
`neo4j_request_family_store.py`'s role. `_DuckDBRequestFamilyMixin` is
combined into the public `DuckDBGraphStore` class via multiple
inheritance; every method here relies on `self._call(...)` existing on
whatever it ends up mixed into.

Unlike component families, `RequestFamily`/method-grouping is dropped here:
`InferredRequest` carries its own `method` field and nothing in `GraphStore`
ever reads a request's family membership back - Neo4j's `:RequestFamily`
node exists only for its own Browser-coloring convenience (same category as
`apply_tag_labels`), which has no equivalent in an embedded store. The
`inferred_requests` table is the complete, faithful record either way.

Details: docs/dev/database/_duckdb_request_family_store.md#module
"""
from __future__ import annotations

import json
from typing import List

from core.interfaces import InferredRequest


class _DuckDBRequestFamilyMixin:
    """Details: docs/dev/database/_duckdb_request_family_store.md#_duckdbrequestfamilymixin"""

    def record_inferred_requests(self, site: str, requests: List[InferredRequest]) -> None:
        def op(conn) -> None:
            # Full rebuild, same reasoning as record_component_families.
            conn.execute(
                "DELETE FROM inferred_request_triggers WHERE request_id IN "
                "(SELECT request_id FROM inferred_requests WHERE site = $site)",
                {"site": site},
            )
            conn.execute("DELETE FROM inferred_requests WHERE site = $site", {"site": site})
            for req in requests:
                request_id = conn.execute(
                    """
                    INSERT INTO inferred_requests (site, method, endpoint, query_params, body_shape,
                                                     response_shape, loaded_by, status_codes,
                                                     latencies_ms, auth_schemes, media_types)
                    VALUES ($site, $method, $endpoint, $query_params, $body_shape,
                            $response_shape, $loaded_by, $status_codes,
                            $latencies_ms, $auth_schemes, $media_types)
                    RETURNING request_id
                    """,
                    {
                        "site": site, "method": req.method, "endpoint": req.endpoint,
                        "query_params": json.dumps(list(req.query_params)),
                        "body_shape": req.body_shape, "response_shape": req.response_shape,
                        "loaded_by": json.dumps(list(req.loaded_by)),
                        "status_codes": json.dumps(list(req.status_codes)),
                        "latencies_ms": json.dumps(list(req.latencies_ms)),
                        "auth_schemes": json.dumps(list(req.auth_schemes)),
                        "media_types": json.dumps(list(req.media_types)),
                    },
                ).fetchone()[0]
                # Same silent-skip contract as component families: a
                # triggered_by entry that doesn't resolve to a real
                # Component is dropped rather than raising - the request
                # itself is still recorded either way (it can legitimately
                # have zero triggers, e.g. a page-load-fired endpoint).
                for page_url, path in req.triggered_by:
                    exists = conn.execute(
                        "SELECT 1 FROM components WHERE site = $site AND page_url = $page_url AND path = $path",
                        {"site": site, "page_url": page_url, "path": path},
                    ).fetchone()
                    if exists:
                        conn.execute(
                            "INSERT INTO inferred_request_triggers (request_id, page_url, path) "
                            "VALUES ($request_id, $page_url, $path)",
                            {"request_id": request_id, "page_url": page_url, "path": path},
                        )

        self._call(op)

    def get_inferred_requests(self, site: str) -> List[InferredRequest]:
        def op(conn) -> List[InferredRequest]:
            rows = conn.execute(
                "SELECT request_id, method, endpoint, query_params, body_shape, response_shape, "
                "loaded_by, status_codes, latencies_ms, auth_schemes, media_types "
                "FROM inferred_requests WHERE site = $site",
                {"site": site},
            ).fetchall()
            result: List[InferredRequest] = []
            for (
                request_id, method, endpoint, query_params, body_shape, response_shape,
                loaded_by, status_codes, latencies_ms, auth_schemes, media_types,
            ) in rows:
                triggers = conn.execute(
                    "SELECT page_url, path FROM inferred_request_triggers WHERE request_id = $request_id "
                    "ORDER BY page_url, path",
                    {"request_id": request_id},
                ).fetchall()
                result.append(
                    InferredRequest(
                        method=method, endpoint=endpoint,
                        query_params=tuple(json.loads(query_params)),
                        body_shape=body_shape or "", response_shape=response_shape or "",
                        triggered_by=tuple((t[0], t[1]) for t in triggers),
                        loaded_by=tuple(json.loads(loaded_by)),
                        status_codes=tuple(json.loads(status_codes)),
                        latencies_ms=tuple(json.loads(latencies_ms)),
                        auth_schemes=tuple(json.loads(auth_schemes)),
                        media_types=tuple(json.loads(media_types)),
                    )
                )
            return result

        return self._call(op)
