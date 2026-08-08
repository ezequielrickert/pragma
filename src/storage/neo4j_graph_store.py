"""Neo4j-backed GraphStore implementation.

This is the single place that knows about NEO4J_HOST/PORT/USER/PASSWORD/
DATABASE - no other module should read those env vars directly, mirroring
the per-provider Config pattern used by every agent (e.g. LocalConfig in
src/agents/local_agent.py).
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

# The driver logs a WARNING-level "unknown relationship type/property" notification
# whenever a query references NAVIGATED_TO/component before any edge has ever been
# created (e.g. the very first get_loop_signals call on a fresh site) - expected on
# a new site's first pages, not an actual problem, so it's silenced rather than left
# to print via Python logging's default stderr handler and read like a real error.
logging.getLogger("neo4j").setLevel(logging.ERROR)

# Shared filter clause for the `semantic_only` component queries below - excludes
# the cursor:pointer catch-all layer (capped, noisier than the ARIA/semantic
# selector) from unexplored-component counts and completion-guard checks.
_SEMANTIC_ONLY_CLAUSE = " WHERE c.layer <> 'pointer'"


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
        if not self.password:
            # Sending auth=(user, None) doesn't fail client-side - the driver happily ships
            # a malformed token and lets the *server* reject it, logging a cryptic
            # "Unsupported authentication token, missing key `credentials`" WARN with no
            # indication of why (seen repeatedly in practice: every code path that touches
            # Neo4jGraphStore without first going through `src/cli.py`'s load_dotenv() -
            # e.g. a bare `python -c` script, or pytest collecting this module - hits this
            # if NEO4J_PASSWORD is only set in .env and not the shell). Failing fast here
            # with an actionable message is strictly better than one more silent retry
            # against the server.
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
                    p.visited_at = $visited_at
                ON MATCH SET
                    p.status = CASE WHEN $status <> 'Pending' THEN $status ELSE p.status END,
                    p.components = CASE WHEN $status <> 'Pending' THEN $components ELSE p.components END,
                    p.context = CASE WHEN $context <> '' THEN $context ELSE p.context END,
                    p.label = CASE WHEN $label <> '' THEN $label ELSE p.label END,
                    p.description = CASE WHEN $description <> '' THEN $description ELSE p.description END,
                    p.title = CASE WHEN $title <> '' THEN $title ELSE p.title END,
                    p.visited_at = CASE WHEN $status = 'Finished' THEN $visited_at ELSE p.visited_at END
                MERGE (s)-[:HAS_PAGE]->(p)
                """,
                site=site, url=url, status=status, components=components,
                context=context, label=label, description=description, title=title, visited_at=visited_at,
            )

    def get_page_descriptions(self, site: str) -> Dict[str, str]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:Page {site: $site})
                WHERE p.description IS NOT NULL AND p.description <> ''
                RETURN p.url AS url, p.description AS description
                """,
                site=site,
            )
            return {r["url"]: r["description"] for r in result}

    def get_page_titles(self, site: str) -> Dict[str, str]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:Page {site: $site})
                WHERE p.title IS NOT NULL AND p.title <> ''
                RETURN p.url AS url, p.title AS title
                """,
                site=site,
            )
            return {r["url"]: r["title"] for r in result}

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

    def clear_site(self, site: str) -> None:
        # DETACH DELETE on every Page tagged with this site removes all of its
        # incident relationships too (NAVIGATED_TO, DISCOVERED_LINK, HAS_PAGE),
        # regardless of which node "owns" them - no separate relationship
        # query needed. The Site node is deleted in the same pass since
        # nothing else references it once its pages are gone. Component nodes
        # are a separate label, so a Page-scoped DETACH DELETE does not reach
        # them - they'd otherwise survive (orphaned, still matching this
        # site's Component queries) after every "fresh" purge.
        with self._session() as session:
            session.run("MATCH (p:Page {site: $site}) DETACH DELETE p", site=site)
            session.run("MATCH (c:Component {site: $site}) DETACH DELETE c", site=site)
            session.run("MATCH (t:TextContent {site: $site}) DETACH DELETE t", site=site)
            session.run("MATCH (s:Site {name: $site}) DETACH DELETE s", site=site)

    def record_component(
        self,
        site: str,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        role: str = "",
        input_type: str = "",
        visible: bool = True,
        layer: str = "semantic",
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
        component_type: str = "",
    ) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (p:Page {site: $site, url: $page_url})
                    ON CREATE SET p.status = 'Pending', p.components = 0, p.context = '-', p.label = '-'
                MERGE (c:Component {site: $site, page_url: $page_url, path: $path})
                ON CREATE SET
                    c.tag = $tag, c.text = $text, c.role = $role, c.input_type = $input_type,
                    c.visible = $visible, c.layer = $layer,
                    c.x = $x, c.y = $y, c.width = $width, c.height = $height,
                    c.component_type = $component_type, c.options = '',
                    c.interacted = false, c.interactions = [], c.network_requests = []
                ON MATCH SET
                    c.tag = $tag, c.text = $text, c.role = $role, c.input_type = $input_type,
                    c.visible = $visible, c.layer = $layer,
                    c.x = $x, c.y = $y, c.width = $width, c.height = $height,
                    c.component_type = $component_type
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, tag=tag, text=text,
                role=role, input_type=input_type, visible=visible, layer=layer,
                x=x, y=y, width=width, height=height, component_type=component_type,
            )

    def record_component_interaction(
        self,
        site: str,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
    ) -> None:
        entry = json.dumps({"action": action, "value": value, "resulting_url": resulting_url})
        with self._session() as session:
            session.run(
                """
                MERGE (p:Page {site: $site, url: $page_url})
                    ON CREATE SET p.status = 'Pending', p.components = 0, p.context = '-', p.label = '-'
                MERGE (c:Component {site: $site, page_url: $page_url, path: $path})
                ON CREATE SET
                    c.tag = '', c.text = '', c.role = '', c.input_type = '',
                    c.visible = true, c.layer = 'semantic', c.component_type = '', c.options = '',
                    c.interacted = false, c.interactions = [], c.network_requests = []
                SET c.interacted = true, c.interactions = c.interactions + $entry
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, entry=entry,
            )

    def record_component_options(self, site: str, page_url: str, path: str, options: str) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (p:Page {site: $site, url: $page_url})
                    ON CREATE SET p.status = 'Pending', p.components = 0, p.context = '-', p.label = '-'
                MERGE (c:Component {site: $site, page_url: $page_url, path: $path})
                ON CREATE SET
                    c.tag = '', c.text = '', c.role = '', c.input_type = '',
                    c.visible = true, c.layer = 'semantic', c.component_type = '',
                    c.interacted = false, c.interactions = [], c.network_requests = []
                SET c.options = $options
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, options=options,
            )

    def record_component_network(self, site: str, page_url: str, path: str, requests_json: str) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (p:Page {site: $site, url: $page_url})
                    ON CREATE SET p.status = 'Pending', p.components = 0, p.context = '-', p.label = '-'
                MERGE (c:Component {site: $site, page_url: $page_url, path: $path})
                ON CREATE SET
                    c.tag = '', c.text = '', c.role = '', c.input_type = '',
                    c.visible = true, c.layer = 'semantic', c.component_type = '', c.options = '',
                    c.interacted = false, c.interactions = [], c.network_requests = []
                SET c.network_requests = c.network_requests + $entry
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, entry=requests_json,
            )

    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (c:Component {site: $site, page_url: $page_url})
                RETURN c.path AS path, c.tag AS tag, c.text AS text,
                       c.interacted AS interacted, c.visible AS visible,
                       c.component_type AS component_type, c.options AS options,
                       c.x AS x, c.y AS y, c.width AS width, c.height AS height,
                       c.network_requests AS network_requests
                """,
                site=site, page_url=page_url,
            )
            return {
                r["path"]: {
                    "tag": r["tag"], "text": r["text"],
                    "interacted": r["interacted"], "visible": r["visible"],
                    "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
                    "component_type": r["component_type"] or "", "options": r["options"] or "",
                    "network_requests": [req for batch in (r["network_requests"] or []) for req in json.loads(batch)],
                }
                for r in result
            }

    def count_unexplored_components(self, site: str, semantic_only: bool = True) -> Tuple[int, int]:
        query = "MATCH (c:Component {site: $site})"
        if semantic_only:
            query += _SEMANTIC_ONLY_CLAUSE
        query += (
            " RETURN sum(CASE WHEN c.interacted THEN 0 ELSE 1 END) AS unexplored, count(c) AS total"
        )
        with self._session() as session:
            record = session.run(query, site=site).single()
            return (record["unexplored"] or 0, record["total"] or 0) if record else (0, 0)

    def get_pages_with_unexplored_components(
        self, site: str, limit: Optional[int] = None, semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        query = "MATCH (c:Component {site: $site, interacted: false})"
        if semantic_only:
            query += _SEMANTIC_ONLY_CLAUSE
        query += (
            " RETURN c.page_url AS url, count(c) AS unexplored_count"
            " ORDER BY unexplored_count DESC"
        )
        params: Dict[str, Any] = {"site": site}
        if limit is not None:
            query += " LIMIT $limit"
            params["limit"] = limit
        with self._session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        query = "MATCH (c:Component {site: $site, page_url: $url, interacted: false})"
        if semantic_only:
            query += _SEMANTIC_ONLY_CLAUSE
        query += " RETURN c LIMIT 1"
        with self._session() as session:
            return session.run(query, site=site, url=url).single() is not None

    def get_component_ledger(self, site: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (c:Component {site: $site})
                RETURN c.page_url AS page_url, c.path AS path, c.tag AS tag, c.text AS text,
                       c.interacted AS interacted, c.interactions AS interactions,
                       c.x AS x, c.y AS y, c.width AS width, c.height AS height,
                       c.component_type AS component_type, c.options AS options,
                       c.network_requests AS network_requests
                """,
                site=site,
            )
            ledger: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for r in result:
                page = ledger.setdefault(r["page_url"], {})
                page[r["path"]] = {
                    "tag": r["tag"],
                    "text": r["text"],
                    "interacted": r["interacted"],
                    "interactions": [json.loads(e) for e in (r["interactions"] or [])],
                    "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
                    "component_type": r["component_type"] or "", "options": r["options"] or "",
                    "network_requests": [req for batch in (r["network_requests"] or []) for req in json.loads(batch)],
                }
            return ledger

    def record_text_content(
        self,
        site: str,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        visible: bool = True,
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> None:
        with self._session() as session:
            session.run(
                """
                MERGE (p:Page {site: $site, url: $page_url})
                    ON CREATE SET p.status = 'Pending', p.components = 0, p.context = '-', p.label = '-'
                MERGE (t:TextContent {site: $site, page_url: $page_url, path: $path})
                ON CREATE SET
                    t.tag = $tag, t.text = $text, t.visible = $visible,
                    t.x = $x, t.y = $y, t.width = $width, t.height = $height
                ON MATCH SET
                    t.tag = $tag, t.text = $text, t.visible = $visible,
                    t.x = $x, t.y = $y, t.width = $width, t.height = $height
                MERGE (p)-[:HAS_TEXT]->(t)
                """,
                site=site, page_url=page_url, path=path, tag=tag, text=text,
                visible=visible, x=x, y=y, width=width, height=height,
            )

    def get_text_content_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (t:TextContent {site: $site})
                RETURN t.page_url AS page_url, t.path AS path, t.tag AS tag, t.text AS text,
                       t.visible AS visible, t.x AS x, t.y AS y, t.width AS width, t.height AS height
                """,
                site=site,
            )
            ledger: Dict[str, List[Dict[str, Any]]] = {}
            for r in result:
                ledger.setdefault(r["page_url"], []).append(
                    {
                        "path": r["path"], "tag": r["tag"], "text": r["text"], "visible": r["visible"],
                        "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
                    }
                )
            return ledger
