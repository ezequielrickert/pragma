"""Static-text-content write path for `LadybugGraphStore` - split from
`component.py`/`page.py` for the same file-size reason the retired
DuckDB backend split `_duckdb_text_content_store.py` out on its own.
`_LadybugTextContentMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)`/
`self._ensure_page(...)` (defined on `page.py`'s mixin, resolved through
`LadybugGraphStore`'s MRO) existing on whatever it ends up mixed into.

Storage-migration plan step 4.

Details: docs/dev/database/ladybug/text_content.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._cypher import set_clause

_FIELDS = ("tag", "text", "visible", "x", "y", "width", "height")
_SET_CLAUSE = set_clause("t", _FIELDS)
_SET_CLAUSE_UNWIND = set_clause("t", _FIELDS, row_alias="r.")


class _LadybugTextContentMixin:
    """Details: docs/dev/database/ladybug/text_content.md#_ladybugtextcontentmixin"""

    def record_text_content(
        self,
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
        """Create or refresh a text-content record; called once per page visit.
        Details: docs/dev/database/ladybug/text_content.md#record_text_content
        """
        params = {
            "id": f"{page_url}|{path}", "path": path, "tag": tag, "text": text,
            "visible": visible, "x": x, "y": y, "width": width, "height": height,
        }

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            conn.execute(
                f"""
                MERGE (t:TextContent {{id: $id}})
                ON CREATE SET t.path = $path, {_SET_CLAUSE}
                ON MATCH SET {_SET_CLAUSE}
                WITH t
                MATCH (p:Page {{url: $page_url}})
                MERGE (p)-[:HAS_TEXT]->(t)
                """,
                {**params, "page_url": page_url},
            )

        self._call(op)

    def record_text_contents(self, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Batched `record_text_content`: one `UNWIND` for a whole page
        visit's text inventory instead of one round-trip per node.
        Details: docs/dev/database/ladybug/text_content.md#record_text_contents
        """
        if not entries:
            return
        rows = [
            {
                "id": f"{page_url}|{item['path']}", "path": item["path"],
                "tag": item.get("tag", ""), "text": item.get("text", ""),
                "visible": item.get("visible", True),
                "x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height"),
            }
            for item in entries
        ]

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            # MATCH the page before UNWIND, not after via a WITH - a MATCH
            # following a WITH that itself follows an UNWIND raised "Cannot
            # evaluate expression with type VARIABLE" against the real
            # engine (confirmed live; the single-item, non-UNWIND version
            # of this same WITH shape works fine). Matching the page once
            # up front and carrying it through the UNWIND sidesteps it.
            conn.execute(
                f"""
                MATCH (p:Page {{url: $page_url}})
                UNWIND $rows AS r
                MERGE (t:TextContent {{id: r.id}})
                ON CREATE SET t.path = r.path, {_SET_CLAUSE_UNWIND}
                ON MATCH SET {_SET_CLAUSE_UNWIND}
                MERGE (p)-[:HAS_TEXT]->(t)
                """,
                {"rows": rows, "page_url": page_url},
            )

        self._call(op)

    def get_text_content_ledger(self) -> Dict[str, List[Dict[str, Any]]]:
        """`{page_url: [{"path", "tag", "text", "visible", "x", "y",
        "width", "height"}, ...]}` for the whole site.
        Details: docs/dev/database/ladybug/text_content.md#get_text_content_ledger
        """
        def op(conn) -> Dict[str, List[Dict[str, Any]]]:
            rows = conn.execute(
                """
                MATCH (p:Page)-[:HAS_TEXT]->(t:TextContent)
                RETURN p.url, t.path, t.tag, t.text, t.visible, t.x, t.y, t.width, t.height
                """
            )
            ledger: Dict[str, List[Dict[str, Any]]] = {}
            for page_url, path, tag, text, visible, x, y, width, height in rows:
                ledger.setdefault(page_url, []).append(
                    {"path": path, "tag": tag, "text": text, "visible": visible, "x": x, "y": y, "width": width, "height": height}
                )
            return ledger

        return self._call(op)
