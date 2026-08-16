"""Component CRUD for `Neo4jGraphStore` - split out of `neo4j_graph_store.py`
to keep that file under this project's file-size threshold (see
`.claude/skills/file-size-audit`). `_Neo4jComponentMixin` is combined into
the public `Neo4jGraphStore` class there via multiple inheritance; it is
never instantiated on its own, and every method here relies on
`self._session()` existing on whatever it ends up mixed into.
Details: docs/dev/database/neo4j_component_store.md#module
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import ComponentFacts, VisitStep
from ._neo4j_cypher_helpers import (
    _COMPONENT_BLANK_STUB,
    _COMPONENT_DESCRIPTIVE_SET,
    _COMPONENT_DESCRIPTIVE_SET_FROM_ROW,
    _COMPONENT_FACTS_RETURN,
    _FACTS_FIELDS,
    _INTERACTIONS_COLLECT,
    _SEMANTIC_ONLY_CLAUSE,
    _page_ensure_clause,
)


class _Neo4jComponentMixin:
    """Details: docs/dev/database/neo4j_component_store.md#_neo4jcomponentmixin"""

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
        facts: Optional[ComponentFacts] = None,
    ) -> None:
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                MERGE (c:Component {{site: $site, page_url: $page_url, path: $path}})
                ON CREATE SET
                    {_COMPONENT_DESCRIPTIVE_SET},
                    c.options = '', c.interacted = false, c.interaction_count = 0, c.network_requests = []
                ON MATCH SET
                    {_COMPONENT_DESCRIPTIVE_SET}
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, tag=tag, text=text,
                role=role, input_type=input_type, visible=visible, layer=layer,
                x=x, y=y, width=width, height=height, component_type=component_type,
                **asdict(facts or ComponentFacts()),
            )

    def record_components(self, site: str, page_url: str, components: List[Dict[str, Any]]) -> None:
        """Batched `record_component`: one UNWIND MERGE for a whole discovery
        pass's components instead of one Cypher round-trip each - collapses
        the 100-300+ individual writes a component-heavy real page produced.
        Details: docs/dev/database/neo4j_graph_store.md#record_components
        """
        if not components:
            return
        rows = [
            {
                "path": item["path"],
                "tag": item.get("tag", ""),
                "text": item.get("text", ""),
                "role": item.get("role", ""),
                "input_type": item.get("input_type", ""),
                "visible": item.get("visible", True),
                "layer": item.get("layer", "semantic"),
                "x": item.get("x"), "y": item.get("y"),
                "width": item.get("width"), "height": item.get("height"),
                "component_type": item.get("component_type", ""),
                **asdict(item.get("facts") or ComponentFacts()),
            }
            for item in components
        ]
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                WITH p
                UNWIND $rows AS row
                MERGE (c:Component {{site: $site, page_url: $page_url, path: row.path}})
                ON CREATE SET
                    {_COMPONENT_DESCRIPTIVE_SET_FROM_ROW},
                    c.options = '', c.interacted = false, c.interaction_count = 0, c.network_requests = []
                ON MATCH SET
                    {_COMPONENT_DESCRIPTIVE_SET_FROM_ROW}
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, rows=rows,
            )

    def record_component_interaction(
        self,
        site: str,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
        source_path: str = "",
        step: Optional[VisitStep] = None,
    ) -> None:
        # An interaction that navigated points at where it landed; one that
        # didn't points back at its own page, so every interaction is a
        # traversable edge rather than a string buried in an array.
        # Details: docs/dev/database/neo4j_component_store.md#interacted
        target_url = resulting_url or page_url
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                MERGE (c:Component {{site: $site, page_url: $page_url, path: $path}})
                {_COMPONENT_BLANK_STUB}
                SET c.interacted = true,
                    c.interaction_count = coalesce(c.interaction_count, 0) + 1
                MERGE (p)-[:HAS_COMPONENT]->(c)
                WITH c
                {_page_ensure_clause("target", "target_url")}
                CREATE (c)-[:INTERACTED {{
                    site: $site, action: $action, value: $value,
                    resulting_url: $resulting_url, source_path: $source_path,
                    navigated: $navigated, seq: c.interaction_count, created_at: $created_at,
                    visit_id: $visit_id, step_seq: $step_seq
                }}]->(target)
                """,
                site=site, page_url=page_url, path=path, action=action, value=value,
                resulting_url=resulting_url, source_path=source_path, target_url=target_url,
                navigated=bool(resulting_url) and resulting_url != page_url,
                created_at=datetime.now(timezone.utc).isoformat(),
                visit_id=step.visit_id if step else "", step_seq=step.seq if step else 0,
            )

    def record_component_options(
        self, site: str, page_url: str, path: str, options: Dict[str, Any], option_labels: Optional[List[str]] = None
    ) -> None:
        # `options` is a genuine union type (see GraphStore's own
        # docstring) - JSON-encoding it into c.options is this backend's
        # storage detail; every reader (describe_options) already expects
        # that string back, unchanged.
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                MERGE (c:Component {{site: $site, page_url: $page_url, path: $path}})
                {_COMPONENT_BLANK_STUB}
                SET c.options = $options, c.option_labels = $option_labels
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, options=json.dumps(options),
                option_labels=option_labels or [],
            )

    def record_component_network(self, site: str, page_url: str, path: str, requests: List[Dict[str, Any]]) -> None:
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                MERGE (c:Component {{site: $site, page_url: $page_url, path: $path}})
                {_COMPONENT_BLANK_STUB}
                SET c.network_requests = c.network_requests + $entry
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, path=path, entry=json.dumps(requests),
            )

    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        with self._session() as session:
            result = session.run(
                f"""
                MATCH (c:Component {{site: $site, page_url: $page_url}})
                RETURN c.path AS path, c.tag AS tag, c.text AS text,
                       c.interacted AS interacted, c.visible AS visible,
                       c.component_type AS component_type, c.options AS options,
                       c.option_labels AS option_labels,
                       c.x AS x, c.y AS y, c.width AS width, c.height AS height,
                       c.network_requests AS network_requests, {_COMPONENT_FACTS_RETURN}
                """,
                site=site, page_url=page_url,
            )
            return {
                r["path"]: {
                    "tag": r["tag"], "text": r["text"],
                    "interacted": r["interacted"], "visible": r["visible"],
                    "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
                    "component_type": r["component_type"] or "", "options": r["options"] or "",
                    "option_labels": list(r["option_labels"] or []),
                    "network_requests": [req for batch in (r["network_requests"] or []) for req in json.loads(batch)],
                    **{name: r[name] for name in _FACTS_FIELDS},
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
                f"""
                MATCH (c:Component {{site: $site}})
                {_INTERACTIONS_COLLECT}
                RETURN c.page_url AS page_url, c.path AS path, c.tag AS tag, c.text AS text,
                       c.role AS role, c.input_type AS input_type,
                       c.visible AS visible, c.layer AS layer,
                       c.interacted AS interacted, interactions,
                       c.x AS x, c.y AS y, c.width AS width, c.height AS height,
                       c.component_type AS component_type, c.options AS options,
                       c.option_labels AS option_labels,
                       c.network_requests AS network_requests, {_COMPONENT_FACTS_RETURN}
                """,
                site=site,
            )
            ledger: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for r in result:
                page = ledger.setdefault(r["page_url"], {})
                page[r["path"]] = {
                    "tag": r["tag"],
                    "text": r["text"],
                    # See memory_graph_store.get_component_ledger for why
                    # these four were added - `layer` gates a filter that
                    # silently never fired without it.
                    "role": r["role"] or "",
                    "input_type": r["input_type"] or "",
                    "visible": r["visible"] if r["visible"] is not None else True,
                    "layer": r["layer"] or "semantic",
                    "interacted": r["interacted"],
                    "interactions": [dict(entry) for entry in r["interactions"]],
                    "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
                    "component_type": r["component_type"] or "", "options": r["options"] or "",
                    "option_labels": list(r["option_labels"] or []),
                    "network_requests": [req for batch in (r["network_requests"] or []) for req in json.loads(batch)],
                    **{name: r[name] for name in _FACTS_FIELDS},
                }
            return ledger

    def record_component_ancestors(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Stored as a JSON-encoded property (`c.ancestors`), not a real
        `CONTAINS` relationship to a separate container node: the
        structural ancestors here (nav/section/aside/...) are almost never
        themselves discovered as `:Component` nodes (discovery only
        matches interactive elements), so there is no existing node to
        point an edge at without inventing a second node type this backend
        doesn't otherwise model. DuckDB gets the real relational table
        (`containment`, see `_duckdb_containment_store.py`) instead.
        """
        if not entries:
            return
        rows = [{"path": e["path"], "ancestors": json.dumps(e.get("ancestors") or [])} for e in entries]
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                WITH p
                UNWIND $rows AS row
                MERGE (c:Component {{site: $site, page_url: $page_url, path: row.path}})
                {_COMPONENT_BLANK_STUB}
                SET c.ancestors = row.ancestors
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                site=site, page_url=page_url, rows=rows,
            )

    def get_containment_ledger(self, site: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        with self._session() as session:
            result = session.run(
                """
                MATCH (c:Component {site: $site})
                WHERE c.ancestors IS NOT NULL AND c.ancestors <> '[]'
                RETURN c.page_url AS page_url, c.path AS path, c.ancestors AS ancestors
                """,
                site=site,
            )
            ledger: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            for r in result:
                ledger.setdefault(r["page_url"], {})[r["path"]] = json.loads(r["ancestors"])
            return ledger
