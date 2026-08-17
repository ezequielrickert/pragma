"""The named, parameterized query library steps 1-8's own `get_*` methods
don't already cover, plus the `query(name, **params)` dispatcher over
all of them - storage-migration plan step 9.
`_LadybugNamedQueriesMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)` existing
on whatever it ends up mixed into.

Per `research/rag-over-neo4j-for-future-qa.md` - a local model must never
drive a raw tool call - this is what a model at that tier is meant to
pick from instead of `raw_query.py`'s escape hatch: a known, bounded set
of questions with no way to express an arbitrary write.

Details: docs/dev/database/ladybug/named_queries.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class _LadybugNamedQueriesMixin:
    """Details: docs/dev/database/ladybug/named_queries.md#_ladybugnamedqueriesmixin"""

    def endpoint_contract(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        """One endpoint's contract - status codes, schemas, auth schemes,
        media types - aggregated from every `Request` that `CALLS` it.
        Unlike `get_inferred_requests()` (which deliberately excludes
        third-party endpoints - it answers "what is this application's
        own API"), this answers "what does this *specific* endpoint look
        like" for whichever `Endpoint.id` is asked about, first- or
        third-party alike.

        Returns:
            `None` if `endpoint_id` names no `Endpoint`. Otherwise a dict
            with `method`/`host`/`path_pattern`/`path_params`/
            `first_party`/`call_count` plus `status_codes`/`auth_schemes`/
            `media_types`/`request_schemas`/`response_schemas` (each a
            sorted list, `[]` for a third-party endpoint with no `Request`
            observations to aggregate).
        Details: docs/dev/database/ladybug/named_queries.md#endpoint_contract
        """
        def op(conn) -> Optional[Dict[str, Any]]:
            endpoint_rows = conn.execute(
                "MATCH (e:Endpoint {id: $id}) RETURN e.method, e.host, e.path_pattern, "
                "e.path_params, e.first_party, e.call_count",
                {"id": endpoint_id},
            )
            endpoint_rows = list(endpoint_rows)
            if not endpoint_rows:
                return None
            method, host, path_pattern, path_params, first_party, call_count = endpoint_rows[0]

            request_rows = conn.execute(
                """
                MATCH (r:Request)-[:CALLS]->(:Endpoint {id: $id})
                RETURN collect(DISTINCT r.status), collect(DISTINCT r.auth_scheme),
                       collect(DISTINCT r.media_type), collect(DISTINCT r.request_schema),
                       collect(DISTINCT r.response_schema)
                """,
                {"id": endpoint_id},
            )
            status_codes, auth_schemes, media_types, request_schemas, response_schemas = next(
                iter(request_rows), ([], [], [], [], [])
            )
            return {
                "method": method, "host": host, "path_pattern": path_pattern,
                "path_params": path_params, "first_party": first_party, "call_count": call_count,
                "status_codes": sorted(s for s in status_codes if s is not None),
                "auth_schemes": sorted(a for a in auth_schemes if a),
                "media_types": sorted(m for m in media_types if m),
                "request_schemas": sorted(s for s in request_schemas if s),
                "response_schemas": sorted(s for s in response_schemas if s),
            }

        return self._call(op)

    def callers_of(self, endpoint_id: str) -> List[Dict[str, str]]:
        """Every `Component` whose interaction reached this endpoint -
        `[{"page_url", "path"}, ...]`, deduplicated, sorted.
        Details: docs/dev/database/ladybug/named_queries.md#callers_of
        """
        def op(conn) -> List[Dict[str, str]]:
            rows = conn.execute(
                """
                MATCH (p:Page)-[:HAS_COMPONENT]->(c:Component)-[:PERFORMED]->
                      (:Interaction)-[:TRIGGERED]->(:Request)-[:CALLS]->(:Endpoint {id: $id})
                RETURN DISTINCT p.url, c.path
                """,
                {"id": endpoint_id},
            )
            return sorted(
                ({"page_url": page_url, "path": path} for page_url, path in rows),
                key=lambda r: (r["page_url"], r["path"]),
            )

        return self._call(op)

    def integrations(self) -> List[Dict[str, Any]]:
        """The third-party inventory - every `Endpoint` this application
        integrates with but doesn't own, busiest first. The counterpart to
        `get_inferred_requests()`'s first-party-only contract.
        Details: docs/dev/database/ladybug/named_queries.md#integrations
        """
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                "MATCH (e:Endpoint {first_party: false}) RETURN e.host, e.method, "
                "e.path_pattern, e.call_count ORDER BY e.call_count DESC"
            )
            return [
                {"host": host, "method": method, "path_pattern": path_pattern, "call_count": call_count}
                for host, method, path_pattern, call_count in rows
            ]

        return self._call(op)

    def flows_from(self, page_url: str, max_hops: int = 6) -> List[str]:
        """Every page reachable from `page_url` within `max_hops`
        `NAVIGATES_TO` steps - a traversal, not a stored aggregate.
        `max_hops` is clamped to `[1, 10]` and interpolated directly into
        the Cypher text rather than bound as a parameter: confirmed
        against the real engine, a variable-length path's hop bound must
        be a literal, not a parameter (`Parser exception` otherwise) -
        safe here since it is a Python `int` this method itself clamps,
        never a caller-supplied string.
        Details: docs/dev/database/ladybug/named_queries.md#flows_from
        """
        hops = max(1, min(int(max_hops), 10))

        def op(conn) -> List[str]:
            rows = conn.execute(
                f"""
                MATCH (:Page {{url: $page_url}})-[:NAVIGATES_TO*1..{hops}]->(target:Page)
                RETURN DISTINCT target.url
                """,
                {"page_url": page_url},
            )
            return sorted(url for (url,) in rows)

        return self._call(op)

    def components_in(self, container_id: str) -> List[Dict[str, str]]:
        """Every `Component` a `Container` contains, direct or nested -
        `CONTAINS*` traversal recovering the full chain `Container`'s own
        direct-edges-only storage doesn't keep as a stored closure.
        Details: docs/dev/database/ladybug/named_queries.md#components_in
        """
        def op(conn) -> List[Dict[str, str]]:
            rows = conn.execute(
                "MATCH (:Container {id: $id})-[:CONTAINS*1..8]->(c:Component) "
                "RETURN DISTINCT c.id, c.path",
                {"id": container_id},
            )
            return sorted(
                ({"id": cid, "path": path} for cid, path in rows), key=lambda r: r["path"]
            )

        return self._call(op)

    def unexplored(self) -> List[Dict[str, Any]]:
        """Parity shim for `get_pending()` under the named-query surface -
        pages the frontier still owes a visit.
        Details: docs/dev/database/ladybug/named_queries.md#unexplored
        """
        return self.get_pending()

    def query(self, name: str, **params: Any) -> Any:
        """Dispatch to one of this store's named, parameterized queries
        by string name - what `research/rag-over-neo4j-for-future-qa.md`
        calls for a model tier that should pick from a known set rather
        than write Cypher freehand. Every method already on this store
        that takes no `site`/no positional-only arguments is reachable
        this way, not just the ones this module itself defines.

        Raises:
            `ValueError` if `name` isn't a real method on this store, or
            names something private (leading `_`) or `raw`/`query`
            itself - `query()` is not allowed to call `raw_query.py`'s
            escape hatch or recurse into itself by name.
        Details: docs/dev/database/ladybug/named_queries.md#query
        """
        if name.startswith("_") or name in ("raw", "query"):
            raise ValueError(f"query() will not dispatch to {name!r}")
        method = getattr(self, name, None)
        if method is None or not callable(method):
            raise ValueError(f"no named query {name!r} on this store")
        return method(**params)
