"""DuckDB-backed GraphStore implementation - Phase 3 of the storage
migration plan. Parity with `Neo4jGraphStore`'s contract (same method
set, same semantics), running on an embedded, single-file DuckDB database
instead of a Neo4j server.

Details: docs/dev/database/duckdb_graph_store.md#module
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import GraphStore
from core.registry import GRAPH_STORE_REGISTRY
from ._duckdb_analysis_store import _DuckDBAnalysisMixin
from ._duckdb_component_family_store import _DuckDBComponentFamilyMixin
from ._duckdb_component_store import _DuckDBComponentMixin
from ._duckdb_containment_store import _DuckDBContainmentMixin
from ._duckdb_page_extras_store import _DuckDBPageExtrasMixin
from ._duckdb_request_family_store import _DuckDBRequestFamilyMixin
from ._duckdb_schema import DDL
from ._duckdb_text_content_store import _DuckDBTextContentMixin
from ._duckdb_writer import DuckDBWriter


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@GRAPH_STORE_REGISTRY.register("duckdb")
class DuckDBGraphStore(
    _DuckDBComponentMixin, _DuckDBComponentFamilyMixin, _DuckDBRequestFamilyMixin,
    _DuckDBTextContentMixin, _DuckDBPageExtrasMixin, _DuckDBContainmentMixin, _DuckDBAnalysisMixin, GraphStore,
):
    """GraphStore backed by an embedded DuckDB database, scoped per site via
    a `site` column on every table (same discipline as `Neo4jGraphStore`'s
    `site` property on every node/relationship). Component/ComponentFamily/
    RequestFamily/TextContent/PageExtras CRUD live in the mixins above, same
    split as the Neo4j backend and for the same file-size reason - this
    class owns connection/schema setup plus Page/Site/navigation-edge CRUD.

    All access - reads included - goes through `self._writer.call(...)`,
    which runs on one dedicated thread. See `_duckdb_writer.py` for why.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        # ":memory:" (DuckDB's own in-process, non-persistent database) is
        # the default so tests/the conformance suite need no filesystem
        # state - the real crawl always passes an explicit path.
        self.path = path or ":memory:"
        self._writer: Optional[DuckDBWriter] = None

    def connect(self) -> None:
        if self._writer is not None:
            return
        self._writer = DuckDBWriter(self.path)
        self._writer.call(lambda conn: conn.execute(DDL))

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def _call(self, fn):
        if self._writer is None:
            self.connect()
        return self._writer.call(fn)

    def _ensure_page(self, conn, site: str, url: str) -> None:
        """Create a bare Pending page if `url` doesn't exist yet - the same
        role `_page_ensure_clause` plays in the Neo4j backend, called by
        every method that references a page it doesn't own the full
        upsert contract for (links, edges, components, text content).
        """
        conn.execute("INSERT INTO sites VALUES ($site) ON CONFLICT DO NOTHING", {"site": site})
        conn.execute(
            """
            INSERT INTO pages (site, url, status, components, context, label, caption, visited_at)
            VALUES ($site, $url, 'Pending', 0, '-', '-', $url, '-')
            ON CONFLICT (site, url) DO NOTHING
            """,
            {"site": site, "url": url},
        )

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
        visited_at = _now_iso() if status == "Finished" else "-"
        params = {
            "site": site, "url": url, "status": status, "components": components,
            "context": context or "-", "label": label or "-",
            "description": description, "title": title,
            "caption": title or url, "visited_at": visited_at,
        }

        def op(conn) -> None:
            conn.execute("INSERT INTO sites VALUES ($site) ON CONFLICT DO NOTHING", {"site": site})
            conn.execute(
                """
                INSERT INTO pages (site, url, status, components, context, label,
                                    description, title, caption, visited_at)
                VALUES ($site, $url, $status, $components, $context, $label,
                        $description, $title, $caption, $visited_at)
                ON CONFLICT (site, url) DO UPDATE SET
                    status = CASE WHEN $status <> 'Pending' THEN $status ELSE pages.status END,
                    components = CASE WHEN $status <> 'Pending' THEN $components ELSE pages.components END,
                    context = CASE WHEN $context <> '-' THEN $context ELSE pages.context END,
                    label = CASE WHEN $label <> '-' THEN $label ELSE pages.label END,
                    description = CASE WHEN $description <> '' THEN $description ELSE pages.description END,
                    title = CASE WHEN $title <> '' THEN $title ELSE pages.title END,
                    caption = CASE WHEN $title <> '' THEN $title ELSE coalesce(pages.caption, $url) END,
                    visited_at = CASE WHEN $status = 'Finished' THEN $visited_at ELSE pages.visited_at END
                """,
                params,
            )

        self._call(op)

    def get_page_descriptions(self, site: str) -> Dict[str, str]:
        return self._get_nonempty_page_field(site, "description")

    def get_page_titles(self, site: str) -> Dict[str, str]:
        return self._get_nonempty_page_field(site, "title")

    def _get_nonempty_page_field(self, site: str, field: str) -> Dict[str, str]:
        def op(conn) -> Dict[str, str]:
            rows = conn.execute(
                f"SELECT url, {field} FROM pages WHERE site = $site AND {field} IS NOT NULL AND {field} <> ''",
                {"site": site},
            ).fetchall()
            return {url: value for url, value in rows}

        return self._call(op)

    def is_visited(self, site: str, url: str) -> bool:
        def op(conn) -> bool:
            row = conn.execute(
                "SELECT status FROM pages WHERE site = $site AND url = $url",
                {"site": site, "url": url},
            ).fetchone()
            return bool(row) and row[0] == "Finished"

        return self._call(op)

    def get_pending(self, site: str, limit: Optional[int] = None) -> List[str]:
        def op(conn) -> List[str]:
            query = "SELECT url FROM pages WHERE site = $site AND status = 'Pending' ORDER BY url"
            if limit is not None:
                query += f" LIMIT {int(limit)}"
            return [row[0] for row in conn.execute(query, {"site": site}).fetchall()]

        return self._call(op)

    def get_page_label(self, site: str, url: str) -> Optional[str]:
        def op(conn) -> Optional[str]:
            row = conn.execute(
                "SELECT label FROM pages WHERE site = $site AND url = $url",
                {"site": site, "url": url},
            ).fetchone()
            return row[0] if row else None

        return self._call(op)

    def record_link(self, site: str, from_url: str, to_url: str, label: str) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, from_url)
            self._ensure_page(conn, site, to_url)
            conn.execute(
                """
                INSERT INTO links (site, from_url, to_url, label) VALUES ($site, $from_url, $to_url, $label)
                ON CONFLICT (site, from_url, to_url) DO UPDATE SET label = $label
                """,
                {"site": site, "from_url": from_url, "to_url": to_url, "label": label},
            )

        self._call(op)

    def get_link_label(self, site: str, from_url: str, to_url: str) -> Optional[str]:
        def op(conn) -> Optional[str]:
            row = conn.execute(
                "SELECT label FROM links WHERE site = $site AND from_url = $from_url AND to_url = $to_url",
                {"site": site, "from_url": from_url, "to_url": to_url},
            ).fetchone()
            return row[0] if row else None

        return self._call(op)

    def record_edge(
        self, site: str, from_url: str, to_url: str, component: str, action: str, run_id: str = "",
    ) -> None:
        created_at = _now_iso()
        params = {
            "site": site, "from_url": from_url, "to_url": to_url,
            "component": component, "action": action, "created_at": created_at, "run_id": run_id,
        }

        def op(conn) -> None:
            self._ensure_page(conn, site, from_url)
            self._ensure_page(conn, site, to_url)
            conn.execute(
                """
                INSERT INTO edges (site, from_url, to_url, component, action,
                                    observation_count, first_seen_run, last_seen_run, created_at)
                VALUES ($site, $from_url, $to_url, $component, $action, 1, $run_id, $run_id, $created_at)
                ON CONFLICT (site, from_url, to_url, component, action) DO UPDATE SET
                    observation_count = edges.observation_count + 1,
                    last_seen_run = CASE WHEN $run_id <> '' THEN $run_id ELSE edges.last_seen_run END
                """,
                params,
            )

        self._call(op)

    def get_edges(self, site: str) -> List[Dict[str, Any]]:
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT from_url, component, action, to_url, observation_count, first_seen_run, last_seen_run
                FROM edges WHERE site = $site ORDER BY created_at
                """,
                {"site": site},
            ).fetchall()
            return [
                {
                    "from": r[0], "component": r[1], "action": r[2], "to": r[3],
                    "observation_count": r[4], "first_seen_run": r[5], "last_seen_run": r[6],
                }
                for r in rows
            ]

        return self._call(op)

    def get_progress_table_rows(self, site: str) -> List[Dict[str, Any]]:
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT url, status, components, label FROM pages WHERE site = $site
                ORDER BY status <> 'Finished', url
                """,
                {"site": site},
            ).fetchall()
            return [{"url": r[0], "status": r[1], "components": r[2], "label": r[3]} for r in rows]

        return self._call(op)

    def count_visited(self, site: str) -> Tuple[int, int]:
        def op(conn) -> Tuple[int, int]:
            row = conn.execute(
                """
                SELECT sum(CASE WHEN status = 'Finished' THEN 1 ELSE 0 END), count(*)
                FROM pages WHERE site = $site AND status <> 'External'
                """,
                {"site": site},
            ).fetchone()
            return (row[0] or 0, row[1] or 0)

        return self._call(op)

    def get_loop_signals(self, site: str, url: str) -> List[Dict[str, str]]:
        def op(conn) -> List[Dict[str, str]]:
            rows = conn.execute(
                "SELECT DISTINCT component, from_url FROM edges WHERE site = $site AND to_url = $url",
                {"site": site, "url": url},
            ).fetchall()
            return [{"component": r[0], "from": r[1]} for r in rows]

        return self._call(op)

    def clear_site(self, site: str) -> None:
        def op(conn) -> None:
            # Child tables first - component_family_members/
            # inferred_request_triggers carry no `site` column of their own
            # (they're keyed by family_id/request_id, see _duckdb_schema.py),
            # so their rows are found via the parent they belong to.
            conn.execute(
                "DELETE FROM component_family_members WHERE family_id IN "
                "(SELECT family_id FROM component_families WHERE site = $site)",
                {"site": site},
            )
            conn.execute(
                "DELETE FROM inferred_request_triggers WHERE request_id IN "
                "(SELECT request_id FROM inferred_requests WHERE site = $site)",
                {"site": site},
            )
            conn.execute(
                "DELETE FROM accessibility_violation_nodes WHERE violation_id IN "
                "(SELECT violation_id FROM accessibility_violations WHERE site = $site)",
                {"site": site},
            )
            for table in (
                "pages", "links", "edges", "components", "interactions", "text_content",
                "component_families", "inferred_requests",
                "page_metadata", "accessibility_violations", "page_pseudo_styles", "page_tab_order",
                "containment", "stylesheets", "page_metrics", "page_modules",
            ):
                conn.execute(f"DELETE FROM {table} WHERE site = $site", {"site": site})
            conn.execute("DELETE FROM sites WHERE name = $site", {"site": site})
            # payloads is deliberately NOT cleared here - it's content-
            # addressed and has no `site` column at all, so a row could be
            # shared with another site's identical CSS. clear_site's
            # stylesheets DELETE above may just have made some payload rows
            # unreferenced; prune_unreferenced_payloads() is the explicit,
            # separate cleanup for that, not run automatically here.

        self._call(op)

    def prune_unreferenced_payloads(self) -> int:
        """Delete every `payloads` row no `stylesheets` entry references
        any more - the retention mechanism `clear_site` deliberately
        doesn't run itself (see its own comment). Not part of the
        `GraphStore` interface: this is a DuckDB-specific maintenance
        operation, the same "explicit, not automatic" shape as
        `prune_old_runs`/`debug_logs_keep_last` for debug logs - call it
        after a `clear_site`, or periodically, not on every write.

        Returns:
            How many `payloads` rows were deleted.
        """
        def op(conn) -> int:
            result = conn.execute(
                "DELETE FROM payloads WHERE hash NOT IN (SELECT hash FROM stylesheets WHERE hash <> '')"
            )
            return result.fetchone()[0]

        return self._call(op)
