"""Static-text-content CRUD for `DuckDBGraphStore` - mirrors
`neo4j_text_content_store.py`'s role. `_DuckDBTextContentMixin` is combined
into the public `DuckDBGraphStore` class via multiple inheritance; every
method here relies on `self._call(...)` existing on whatever it ends up
mixed into.
Details: docs/dev/database/_duckdb_text_content_store.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_UPSERT_SQL = """
INSERT INTO text_content (site, page_url, path, tag, text, visible, x, y, width, height)
VALUES ($site, $page_url, $path, $tag, $text, $visible, $x, $y, $width, $height)
ON CONFLICT (site, page_url, path) DO UPDATE SET
    tag = $tag, text = $text, visible = $visible, x = $x, y = $y, width = $width, height = $height
"""


class _DuckDBTextContentMixin:
    """Details: docs/dev/database/_duckdb_text_content_store.md#_duckdbtextcontentmixin"""

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
        params = {
            "site": site, "page_url": page_url, "path": path,
            "tag": tag, "text": text, "visible": visible, "x": x, "y": y, "width": width, "height": height,
        }

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.execute(_UPSERT_SQL, params)

        self._call(op)

    def record_text_contents(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Batched `record_text_content`: one `executemany` for a whole page
        visit's text inventory instead of one round-trip per node.
        """
        if not entries:
            return
        rows = [
            {
                "site": site, "page_url": page_url, "path": item["path"],
                "tag": item.get("tag", ""), "text": item.get("text", ""),
                "visible": item.get("visible", True),
                "x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height"),
            }
            for item in entries
        ]

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.executemany(_UPSERT_SQL, rows)

        self._call(op)

    def get_text_content_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        def op(conn) -> Dict[str, List[Dict[str, Any]]]:
            rows = conn.execute(
                "SELECT page_url, path, tag, text, visible, x, y, width, height "
                "FROM text_content WHERE site = $site",
                {"site": site},
            ).fetchall()
            ledger: Dict[str, List[Dict[str, Any]]] = {}
            for page_url, path, tag, text, visible, x, y, width, height in rows:
                ledger.setdefault(page_url, []).append(
                    {"path": path, "tag": tag, "text": text, "visible": visible, "x": x, "y": y, "width": width, "height": height}
                )
            return ledger

        return self._call(op)
