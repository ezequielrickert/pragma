"""Static-text-content CRUD for `Neo4jGraphStore` - split out of
`neo4j_graph_store.py` to keep that file under this project's file-size
threshold. `_Neo4jTextContentMixin` is combined into the public
`Neo4jGraphStore` class there via multiple inheritance; it is never
instantiated on its own, and every method here relies on `self._session()`
existing on whatever it ends up mixed into.
Details: docs/dev/storage/neo4j_text_content_store.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._neo4j_cypher_helpers import _page_ensure_clause


class _Neo4jTextContentMixin:
    """Details: docs/dev/storage/neo4j_text_content_store.md#_neo4jtextcontentmixin"""

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
                f"""
                {_page_ensure_clause("p", "page_url")}
                MERGE (t:TextContent {{site: $site, page_url: $page_url, path: $path}})
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

    def record_text_contents(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Batched `record_text_content`: one UNWIND MERGE for a whole page
        visit's text inventory instead of one round-trip per text node.
        Details: docs/dev/storage/neo4j_graph_store.md#record_text_contents
        """
        if not entries:
            return
        rows = [
            {
                "path": item["path"],
                "tag": item.get("tag", ""),
                "text": item.get("text", ""),
                "visible": item.get("visible", True),
                "x": item.get("x"), "y": item.get("y"),
                "width": item.get("width"), "height": item.get("height"),
            }
            for item in entries
        ]
        with self._session() as session:
            session.run(
                f"""
                {_page_ensure_clause("p", "page_url")}
                WITH p
                UNWIND $rows AS row
                MERGE (t:TextContent {{site: $site, page_url: $page_url, path: row.path}})
                ON CREATE SET
                    t.tag = row.tag, t.text = row.text, t.visible = row.visible,
                    t.x = row.x, t.y = row.y, t.width = row.width, t.height = row.height
                ON MATCH SET
                    t.tag = row.tag, t.text = row.text, t.visible = row.visible,
                    t.x = row.x, t.y = row.y, t.width = row.width, t.height = row.height
                MERGE (p)-[:HAS_TEXT]->(t)
                """,
                site=site, page_url=page_url, rows=rows,
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
