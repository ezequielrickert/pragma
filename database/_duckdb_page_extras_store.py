"""Page-level "extras" CRUD for `DuckDBGraphStore` - `<meta>`, network-load
and stylesheet data that doesn't belong in the core Page/Site/edge file,
split out for the same file-size reason as every other mixin here.
`_DuckDBPageExtrasMixin` is combined into the public `DuckDBGraphStore`
class via multiple inheritance; every method here relies on
`self._call(...)`/`self._ensure_page(...)` existing on whatever it ends up
mixed into.

Unlike `network_requests` (still a JSON-TEXT blob column on `pages` - a
real relational `requests` table with content-addressed bodies is future
work, not part of this pass), metadata and stylesheets get real child
tables here - this is the concrete "structured information pattern" the
storage migration plan exists to deliver. Stylesheets specifically go
through the shared `payloads` content-addressed store (`_duckdb_schema.py`)
rather than embedding CSS text inline, so pages sharing one vendor bundle
cost one payload row, not one per page.

Details: docs/dev/database/_duckdb_page_extras_store.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


class _DuckDBPageExtrasMixin:
    """Details: docs/dev/database/_duckdb_page_extras_store.md#_duckdbpageextrasmixin"""

    def record_page_metadata(self, site: str, page_url: str, metadata: Dict[str, str]) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.execute("DELETE FROM page_metadata WHERE site = $site AND url = $url", {"site": site, "url": page_url})
            if metadata:
                conn.executemany(
                    "INSERT INTO page_metadata (site, url, meta_name, content) VALUES ($site, $url, $meta_name, $content)",
                    [{"site": site, "url": page_url, "meta_name": k, "content": v} for k, v in metadata.items()],
                )

        self._call(op)

    def get_page_metadata(self, site: str) -> Dict[str, Dict[str, str]]:
        def op(conn) -> Dict[str, Dict[str, str]]:
            rows = conn.execute(
                "SELECT url, meta_name, content FROM page_metadata WHERE site = $site", {"site": site}
            ).fetchall()
            result: Dict[str, Dict[str, str]] = {}
            for url, meta_name, content in rows:
                result.setdefault(url, {})[meta_name] = content
            return result

        return self._call(op)

    def record_page_network(self, site: str, page_url: str, requests: List[Dict[str, Any]]) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            existing = conn.execute(
                "SELECT network_requests FROM pages WHERE site = $site AND url = $url",
                {"site": site, "url": page_url},
            ).fetchone()
            batch = json.loads(existing[0]) if existing and existing[0] else []
            batch.extend(requests)
            conn.execute(
                "UPDATE pages SET network_requests = $entry WHERE site = $site AND url = $url",
                {"site": site, "url": page_url, "entry": json.dumps(batch)},
            )

        self._call(op)

    def get_page_network_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        def op(conn):
            rows = conn.execute(
                "SELECT url, network_requests FROM pages "
                "WHERE site = $site AND network_requests IS NOT NULL",
                {"site": site},
            ).fetchall()
            ledger = {url: json.loads(v) for url, v in rows}
            return {url: reqs for url, reqs in ledger.items() if reqs}

        return self._call(op)

    def record_stylesheets(self, site: str, page_url: str, stylesheets: List[Dict[str, Any]]) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            # Replace, not append - a page revisited later gets its
            # stylesheet capture refreshed, not stacked with the last visit's.
            conn.execute(
                "DELETE FROM stylesheets WHERE site = $site AND page_url = $page_url",
                {"site": site, "page_url": page_url},
            )
            payload_rows = [
                {"hash": s["hash"], "byte_length": s["byte_length"], "content": s["excerpt"]}
                for s in stylesheets
                if s.get("hash")
            ]
            if payload_rows:
                # Content-addressed: first writer for a given hash wins,
                # every later one referencing the same CSS text is free.
                conn.executemany(
                    "INSERT INTO payloads (hash, byte_length, content) VALUES ($hash, $byte_length, $content) "
                    "ON CONFLICT (hash) DO NOTHING",
                    payload_rows,
                )
            sheet_rows = [
                {
                    "site": site, "page_url": page_url, "href": s.get("href", ""),
                    "accessible": bool(s.get("accessible", True)), "hash": s.get("hash", ""),
                }
                for s in stylesheets
            ]
            if sheet_rows:
                conn.executemany(
                    "INSERT INTO stylesheets (site, page_url, href, accessible, hash) "
                    "VALUES ($site, $page_url, $href, $accessible, $hash)",
                    sheet_rows,
                )

        self._call(op)

    def get_stylesheets(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        def op(conn) -> Dict[str, List[Dict[str, Any]]]:
            rows = conn.execute(
                """
                SELECT s.page_url, s.href, s.accessible, s.hash,
                       coalesce(p.content, ''), coalesce(p.byte_length, 0)
                FROM stylesheets s
                LEFT JOIN payloads p ON p.hash = s.hash
                WHERE s.site = $site
                """,
                {"site": site},
            ).fetchall()
            result: Dict[str, List[Dict[str, Any]]] = {}
            for page_url, href, accessible, sheet_hash, content, byte_length in rows:
                result.setdefault(page_url, []).append(
                    {
                        "href": href, "accessible": accessible, "hash": sheet_hash,
                        "excerpt": content, "byte_length": byte_length,
                    }
                )
            return result

        return self._call(op)
