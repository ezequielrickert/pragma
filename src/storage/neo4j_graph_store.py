"""Neo4j-backed GraphStore implementation.
Details: docs/dev/storage/neo4j_graph_store.md#module
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from ..core.interfaces import GraphStore
from ..core.registry import GRAPH_STORE_REGISTRY
from ._neo4j_cypher_helpers import (
    _COMPONENT_BLANK_STUB,  # noqa: F401 - re-exported, see module docstring below
    _page_ensure_clause,
    _page_ensure_clause_from_row,
)
from .neo4j_component_family_store import _Neo4jComponentFamilyMixin
from .neo4j_component_store import _Neo4jComponentMixin
from .neo4j_request_family_store import _Neo4jRequestFamilyMixin
from .neo4j_text_content_store import _Neo4jTextContentMixin

# `_page_ensure_clause`/`_COMPONENT_BLANK_STUB` are re-exported (imported
# above, not redefined) for backward compatibility with
# tests/test_neo4j_cypher_helpers.py, written against this module before
# the Page/Component/ComponentFamily/TextContent split
# (docs/dev/storage/neo4j_graph_store.md#module) moved their real
# definitions to `_neo4j_cypher_helpers.py`.

# Silences a harmless WARNING seen on a fresh site's first pages.
# Details: docs/dev/storage/neo4j_graph_store.md#logging-silence
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
class Neo4jGraphStore(
    _Neo4jComponentMixin, _Neo4jComponentFamilyMixin, _Neo4jRequestFamilyMixin, _Neo4jTextContentMixin, GraphStore
):
    """GraphStore backed by a real Neo4j database, scoped per site via a `site` property.
    Component/ComponentFamily/RequestFamily/TextContent CRUD live in the
    mixins above (own files, see each one's module docstring) - this
    class itself owns connection/schema setup plus Page/Site/navigation-
    edge CRUD, the part that doesn't cleanly belong to any single mixin.
    Details: docs/dev/storage/neo4j_graph_store.md#neo4jgraphstore
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
        if not self.password:
            # Fail fast with an actionable message instead of a cryptic server WARN.
            # Details: docs/dev/storage/neo4j_graph_store.md#connect-no-password
            raise RuntimeError(
                "Neo4jGraphStore.connect(): no password configured (NEO4J_PASSWORD is unset "
                "and none was passed explicitly). Set it in .env (see .env.example) or export "
                "it in your shell before running - docker-compose.yml's default is "
                "'pragma-local-dev' unless NEO4J_PASSWORD was set when the container started."
            )
        self._driver = GraphDatabase.driver(
            f"bolt://{self.host}:{self.port}", auth=(self.user, self.password)
        )
        with self._driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT page_site_url IF NOT EXISTS "
                "FOR (p:Page) REQUIRE (p.site, p.url) IS UNIQUE"
            )
            session.run("CREATE INDEX page_site_idx IF NOT EXISTS FOR (p:Page) ON (p.site)")
            session.run(
                "CREATE CONSTRAINT component_identity IF NOT EXISTS "
                "FOR (c:Component) REQUIRE (c.site, c.page_url, c.path) IS UNIQUE"
            )
            session.run("CREATE INDEX component_site_idx IF NOT EXISTS FOR (c:Component) ON (c.site)")
            session.run(
                "CREATE CONSTRAINT text_content_identity IF NOT EXISTS "
                "FOR (t:TextContent) REQUIRE (t.site, t.page_url, t.path) IS UNIQUE"
            )
            session.run("CREATE INDEX text_content_site_idx IF NOT EXISTS FOR (t:TextContent) ON (t.site)")
            session.run("CREATE INDEX component_family_site_idx IF NOT EXISTS FOR (f:ComponentFamily) ON (f.site)")
            session.run("CREATE INDEX request_family_site_idx IF NOT EXISTS FOR (rf:RequestFamily) ON (rf.site)")
            session.run("CREATE INDEX request_site_idx IF NOT EXISTS FOR (r:Request) ON (r.site)")

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
        description: str = "",
        title: str = "",
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
                    p.description = $description,
                    p.title = $title,
                    p.caption = CASE WHEN $title <> '' THEN $title ELSE $url END,
                    p.visited_at = $visited_at
                ON MATCH SET
                    p.status = CASE WHEN $status <> 'Pending' THEN $status ELSE p.status END,
                    p.components = CASE WHEN $status <> 'Pending' THEN $components ELSE p.components END,
                    p.context = CASE WHEN $context <> '' THEN $context ELSE p.context END,
                    p.label = CASE WHEN $label <> '' THEN $label ELSE p.label END,
                    p.description = CASE WHEN $description <> '' THEN $description ELSE p.description END,
                    p.title = CASE WHEN $title <> '' THEN $title ELSE p.title END,
                    p.caption = CASE WHEN $title <> '' THEN $title ELSE coalesce(p.caption, $url) END,
                    p.visited_at = CASE WHEN $status = 'Finished' THEN $visited_at ELSE p.visited_at END
                MERGE (s)-[:HAS_PAGE]->(p)
                """,
                site=site, url=url, status=status, components=components,
                context=context, label=label, description=description, title=title, visited_at=visited_at,
            )

    def get_page_descriptions(self, site: str) -> Dict[str, str]:
        return self._get_nonempty_page_field(site, "description")

    def get_page_titles(self, site: str) -> Dict[str, str]:
        return self._get_nonempty_page_field(site, "title")

    def _get_nonempty_page_field(self, site: str, field: str) -> Dict[str, str]:
        """Shared by `get_page_descriptions`/`get_page_titles`: both wanted the
        identical query, differing only in which `Page` property they read."""
        with self._session() as session:
            result = session.run(
                f"""
                MATCH (p:Page {{site: $site}})
                WHERE p.{field} IS NOT NULL AND p.{field} <> ''
                RETURN p.url AS url, p.{field} AS value
                """,
                site=site,
            )
            return {r["url"]: r["value"] for r in result}

    def record_accessibility_violations(self, site: str, page_url: str, violations_json: str) -> None:
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                SET p.accessibility_violations = $entry
                """,
                site=site, page_url=page_url, entry=violations_json,
            )

    def get_accessibility_violations(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:Page {site: $site})
                WHERE p.accessibility_violations IS NOT NULL
                RETURN p.url AS url, p.accessibility_violations AS violations
                """,
                site=site,
            )
            found = {r["url"]: json.loads(r["violations"]) for r in result}
            return {url: violations for url, violations in found.items() if violations}

    def record_page_network(self, site: str, page_url: str, requests_json: str) -> None:
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                SET p.network_requests = coalesce(p.network_requests, []) + $entry
                """,
                site=site, page_url=page_url, entry=requests_json,
            )

    def get_page_network_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:Page {site: $site})
                WHERE p.network_requests IS NOT NULL AND size(p.network_requests) > 0
                RETURN p.url AS url, p.network_requests AS batches
                """,
                site=site,
            )
            return {
                r["url"]: [request for batch in r["batches"] for request in json.loads(batch)]
                for r in result
            }

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
                f"""
                {_page_ensure_clause("a", "from_url")}
                {_page_ensure_clause("b", "to_url")}
                MERGE (a)-[r:DISCOVERED_LINK {{site: $site}}]->(b)
                SET r.label = $label
                """,
                site=site, from_url=from_url, to_url=to_url, label=label,
            )

    def record_links(self, site: str, from_url: str, links: List[Dict[str, str]]) -> None:
        """Batched `record_link`: one UNWIND MERGE for a page's whole link
        list instead of one round-trip per `<a>` tag.
        Details: docs/dev/storage/neo4j_graph_store.md#record_links
        """
        if not links:
            return
        rows = [{"to_url": item["to_url"], "label": item.get("label", "")} for item in links]
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("a", "from_url")}
                WITH a
                UNWIND $rows AS row
                {_page_ensure_clause_from_row("b", "to_url")}
                MERGE (a)-[r:DISCOVERED_LINK {{site: $site}}]->(b)
                SET r.label = row.label
                """,
                site=site, from_url=from_url, rows=rows,
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
                f"""
                {_page_ensure_clause("a", "from_url")}
                {_page_ensure_clause("b", "to_url")}
                CREATE (a)-[:NAVIGATED_TO {{
                    component: $component, action: $action, site: $site, created_at: $created_at
                }}]->(b)
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

    def clear_site(self, site: str) -> None:
        # DETACH DELETE removes incident relationships too; see doc for labels.
        # Details: docs/dev/storage/neo4j_graph_store.md#clear_site
        with self._session() as session:
            session.run("MATCH (p:Page {site: $site}) DETACH DELETE p", site=site)
            session.run("MATCH (c:Component {site: $site}) DETACH DELETE c", site=site)
            session.run("MATCH (t:TextContent {site: $site}) DETACH DELETE t", site=site)
            session.run("MATCH (f:ComponentFamily {site: $site}) DETACH DELETE f", site=site)
            session.run("MATCH (r:Request {site: $site}) DETACH DELETE r", site=site)
            session.run("MATCH (rf:RequestFamily {site: $site}) DETACH DELETE rf", site=site)
            session.run("MATCH (s:Site {name: $site}) DETACH DELETE s", site=site)
