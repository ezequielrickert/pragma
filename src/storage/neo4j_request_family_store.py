"""Inferred-API-endpoint CRUD for `Neo4jGraphStore` - split out of
`neo4j_graph_store.py` to keep that file under this project's file-size
threshold, same reasoning as `neo4j_component_family_store.py`.
`_Neo4jRequestFamilyMixin` is combined into the public `Neo4jGraphStore`
class there via multiple inheritance; it is never instantiated on its
own, and every method here relies on `self._session()` existing on
whatever it ends up mixed into.

Graph shape this writes/reads:

```
(:RequestFamily {site, method})
    -[:HAS_REQUEST]-> (:Request {site, method, endpoint, query_params,
                                  body_shape, response_shape})
        <-[:TRIGGERS]- (:Component {..., already exists before this runs})
```

`RequestFamily` grouping is a trivial groupby-by-`method` (GET vs. POST
vs. ...), unlike `ComponentFamily`'s real similarity clustering - there's
no algorithm to speak of, so (unlike component families, which are
clustered externally in `request_family.py` before ever reaching this
file) the method grouping happens right here in `record_inferred_requests`.

Details: docs/dev/storage/neo4j_request_family_store.md#module
"""
from __future__ import annotations

from typing import Dict, List

from ..core.interfaces import InferredRequest


class _Neo4jRequestFamilyMixin:
    """Details: docs/dev/storage/neo4j_request_family_store.md#_neo4jrequestfamilymixin"""

    def record_inferred_requests(self, site: str, requests: List[InferredRequest]) -> None:
        """Replace every `:RequestFamily`/`:Request` node for `site` with
        a fresh set built from `requests`.

        Args:
            site: which site's inferred requests to replace.
            requests: the complete new set - see
                `GraphStore.record_inferred_requests`'s docstring for the
                full contract (always a full rebuild).

        Returns:
            None. One `:RequestFamily` node per distinct `method` among
            `requests` (created via `MERGE`, so two requests with the
            same method share one family node); one `:Request` node per
            entry, linked to its family via `HAS_REQUEST` and to every
            triggering `Component` via `TRIGGERS`. Same silent-skip
            behavior as `record_component_families` for a
            `triggered_by` entry that doesn't resolve to a real
            `Component` - the request node still gets created either way.
        """
        with self._session() as session:
            # Full rebuild, not an incremental merge - same reasoning as
            # record_component_families (cluster membership isn't kept
            # stable across runs).
            session.run("MATCH (rf:RequestFamily {site: $site}) DETACH DELETE rf", site=site)
            session.run("MATCH (r:Request {site: $site}) DETACH DELETE r", site=site)
            for req in requests:
                session.run(
                    """
                    MERGE (rf:RequestFamily:Inferred {site: $site, method: $method})
                    ON CREATE SET rf.caption = $method
                    CREATE (r:Request:Inferred {
                        site: $site, method: $method, endpoint: $endpoint,
                        query_params: $query_params, body_shape: $body_shape,
                        response_shape: $response_shape,
                        caption: $method + ' ' + $endpoint
                    })
                    CREATE (rf)-[:HAS_REQUEST]->(r)
                    WITH r
                    UNWIND $triggered_by AS tb
                    MATCH (c:Component {site: $site, page_url: tb[0], path: tb[1]})
                    CREATE (c)-[:TRIGGERS]->(r)
                    """,
                    site=site, method=req.method, endpoint=req.endpoint,
                    query_params=list(req.query_params), body_shape=req.body_shape,
                    response_shape=req.response_shape,
                    triggered_by=[list(tb) for tb in req.triggered_by],
                )

    def get_inferred_requests(self, site: str) -> List[InferredRequest]:
        """Read every `InferredRequest` currently recorded for `site`
        back from Neo4j, reconstructing `triggered_by` from each
        `Request` node's incoming `TRIGGERS` edges.

        Args:
            site: which site's inferred requests to read.

        Returns:
            A list of `InferredRequest`, one per `:Request` node for
            `site` - present even if it has zero `TRIGGERS` edges
            (unlike `get_component_families`, which requires at least
            one `HAS_VARIANT` edge to match: a request can legitimately
            have no known trigger if the component that fired it wasn't
            itself resolvable at write time). `triggered_by` is sorted
            by `(page_url, path)` for a deterministic result, matching
            `request_family.build_inferred_requests`' own pre-sorted
            output.
        """
        with self._session() as session:
            result = session.run(
                """
                MATCH (r:Request {site: $site})
                OPTIONAL MATCH (c:Component {site: $site})-[:TRIGGERS]->(r)
                WITH r, c ORDER BY c.page_url, c.path
                RETURN elementId(r) AS rid, r.method AS method, r.endpoint AS endpoint,
                       r.query_params AS query_params, r.body_shape AS body_shape,
                       r.response_shape AS response_shape,
                       collect(CASE WHEN c IS NOT NULL THEN [c.page_url, c.path] END) AS triggered_by
                """,
                site=site,
            )
            return [
                InferredRequest(
                    method=r["method"],
                    endpoint=r["endpoint"],
                    query_params=tuple(r["query_params"] or []),
                    body_shape=r["body_shape"] or "",
                    response_shape=r["response_shape"] or "",
                    triggered_by=tuple(tuple(tb) for tb in r["triggered_by"] if tb is not None),
                )
                for r in result
            ]
