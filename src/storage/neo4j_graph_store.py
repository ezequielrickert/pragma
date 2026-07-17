"""Neo4j-backed GraphStore implementation.

This is the single place that knows about NEO4J_HOST/PORT/USER/PASSWORD/
DATABASE - no other module should read those env vars directly, mirroring
the per-provider Config pattern used by every agent (e.g. LocalConfig in
src/agents/local_agent.py).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from ..core.interfaces import GraphStore
from ..core.registry import GRAPH_STORE_REGISTRY

# The driver logs a WARNING-level "unknown relationship type/property" notification
# whenever a query references NAVIGATED_TO/component before any edge has ever been
# created (e.g. the very first get_loop_signals call on a fresh site) - expected on
# a new site's first pages, not an actual problem, so it's silenced rather than left
# to print via Python logging's default stderr handler and read like a real error.
logging.getLogger("neo4j").setLevel(logging.ERROR)


@dataclass
class Neo4jConfig:
    """Every setting the Neo4j store needs, and where it comes from."""

    host: str = "localhost"
    port: int = 7687
    user: str = "neo4j"
    password: Optional[str] = None
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        return cls(
            host=os.getenv("NEO4J_HOST", "localhost"),
            port=int(os.getenv("NEO4J_PORT", "7687")),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )


@GRAPH_STORE_REGISTRY.register("neo4j")
class Neo4jGraphStore(GraphStore):
    """GraphStore backed by a real Neo4j database, scoped per site via a `site` property.

    Neo4j Community Edition only supports a single user database, so per-site
    isolation is done by tagging every node/edge with a `site` property and
    scoping every query with it, rather than one database per site.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        config = Neo4jConfig.from_env()
        self.host = host or config.host
        self.port = int(port) if port is not None else config.port
        self.user = user or config.user
        self.password = password if password is not None else config.password
        self.database = database or config.database
        self._driver = None

    def connect(self) -> None:
        self._driver = GraphDatabase.driver(
            f"bolt://{self.host}:{self.port}", auth=(self.user, self.password)
        )
        with self._driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT page_site_url IF NOT EXISTS "
                "FOR (p:Page) REQUIRE (p.site, p.url) IS UNIQUE"
            )
            session.run("CREATE INDEX page_site_idx IF NOT EXISTS FOR (p:Page) ON (p.site)")

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _session(self):
        if self._driver is None:
            self.connect()
        return self._driver.session(database=self.database)

    def upsert_page(
        self,
        site: str,
        url: str,
        status: str = "Pending",
        components: int = 0,
        context: str = "",
        label: str = "",
    ) -> None:
        visited_at = datetime.now(timezone.utc).isoformat() if status == "Finished" else "-"
        with self._session() as session:
            session.run(
                """
                MERGE (s:Site {name: $site})
                MERGE (p:Page {site: $site, url: $url})
                ON CREATE SET
                    p.status = $status, p.components = $components,
                    p.context = CASE WHEN $context <> '' THEN $context ELSE '-' END,
                    p.label = CASE WHEN $label <> '' THEN $label ELSE '-' END,
                    p.visited_at = $visited_at
                ON MATCH SET
                    p.status = CASE WHEN $status <> 'Pending' THEN $status ELSE p.status END,
                    p.components = CASE WHEN $status <> 'Pending' THEN $components ELSE p.components END,
                    p.context = CASE WHEN $context <> '' THEN $context ELSE p.context END,
                    p.label = CASE WHEN $label <> '' THEN $label ELSE p.label END,
                    p.visited_at = CASE WHEN $status = 'Finished' THEN $visited_at ELSE p.visited_at END
                MERGE (s)-[:HAS_PAGE]->(p)
                """,
                site=site, url=url, status=status, components=components,
                context=context, label=label, visited_at=visited_at,
            )

    def is_visited(self, site: str, url: str) -> bool:
        with self._session() as session:
            record = session.run(
                "MATCH (p:Page {site: $site, url: $url}) RETURN p.status AS status",
                site=site, url=url,
            ).single()
            return bool(record) and record["status"] == "Finished"

    def get_pending(self, site: str, limit: Optional[int] = None) -> List[str]:
        query = (
            "MATCH (p:Page {site: $site, status: 'Pending'}) "
            "RETURN p.url AS url ORDER BY p.url"
        )
        params: Dict[str, Any] = {"site": site}
        if limit is not None:
            query += " LIMIT $limit"
            params["limit"] = limit
        with self._session() as session:
            return [record["url"] for record in session.run(query, **params)]

    def get_page_label(self, site: str, url: str) -> Optional[str]:
        with self._session() as session:
            record = session.run(
                "MATCH (p:Page {site: $site, url: $url}) RETURN p.label AS label",
                site=site, url=url,
            ).single()
            return record["label"] if record else None

    def record_link(self, site: str, from_url: str, to_url: str, label: str) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (a:Page {site: $site, url: $from_url})
                    ON CREATE SET a.status = 'Pending', a.components = 0, a.context = '-', a.label = '-'
                MERGE (b:Page {site: $site, url: $to_url})
                    ON CREATE SET b.status = 'Pending', b.components = 0, b.context = '-', b.label = '-'
                MERGE (a)-[r:DISCOVERED_LINK {site: $site}]->(b)
                SET r.label = $label
                """,
                site=site, from_url=from_url, to_url=to_url, label=label,
            )

    def get_link_label(self, site: str, from_url: str, to_url: str) -> Optional[str]:
        with self._session() as session:
            record = session.run(
                """
                MATCH (:Page {site: $site, url: $from_url})-[r:DISCOVERED_LINK {site: $site}]
                    ->(:Page {site: $site, url: $to_url})
                RETURN r.label AS label
                """,
                site=site, from_url=from_url, to_url=to_url,
            ).single()
            return record["label"] if record else None

    def record_edge(self, site: str, from_url: str, to_url: str, component: str, action: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._session() as session:
            session.run(
                """
                MERGE (a:Page {site: $site, url: $from_url})
                    ON CREATE SET a.status = 'Pending', a.components = 0, a.context = '-', a.label = '-'
                MERGE (b:Page {site: $site, url: $to_url})
                    ON CREATE SET b.status = 'Pending', b.components = 0, b.context = '-', b.label = '-'
                CREATE (a)-[:NAVIGATED_TO {
                    component: $component, action: $action, site: $site, created_at: $created_at
                }]->(b)
                """,
                site=site, from_url=from_url, to_url=to_url,
                component=component, action=action, created_at=created_at,
            )

    def get_edges(self, site: str) -> List[Dict[str, str]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (a:Page {site: $site})-[r:NAVIGATED_TO {site: $site}]->(b:Page {site: $site})
                RETURN a.url AS from, r.component AS component, r.action AS action, b.url AS to
                ORDER BY r.created_at
                """,
                site=site,
            )
            return [
                {"from": r["from"], "component": r["component"], "action": r["action"], "to": r["to"]}
                for r in result
            ]

    def get_progress_table_rows(self, site: str) -> List[Dict[str, Any]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:Page {site: $site})
                RETURN p.url AS url, p.status AS status, p.components AS components, p.label AS label
                ORDER BY p.status <> 'Finished', p.url
                """,
                site=site,
            )
            return [dict(r) for r in result]

    def count_visited(self, site: str) -> Tuple[int, int]:
        with self._session() as session:
            record = session.run(
                """
                MATCH (p:Page {site: $site})
                RETURN sum(CASE WHEN p.status = 'Finished' THEN 1 ELSE 0 END) AS finished, count(p) AS total
                """,
                site=site,
            ).single()
            return (record["finished"] or 0, record["total"] or 0)

    def get_loop_signals(self, site: str, url: str) -> List[Dict[str, str]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (a:Page)-[r:NAVIGATED_TO {site: $site}]->(b:Page {site: $site, url: $url})
                RETURN DISTINCT r.component AS component, a.url AS from
                """,
                site=site, url=url,
            )
            return [{"component": r["component"], "from": r["from"]} for r in result]
