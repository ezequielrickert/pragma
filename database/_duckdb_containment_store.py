"""Structural-containment CRUD for `DuckDBGraphStore` - split out for the
same file-size reason as every other mixin here. `_DuckDBContainmentMixin`
is combined into the public `DuckDBGraphStore` class via multiple
inheritance; every method here relies on `self._call(...)`/
`self._ensure_page(...)` existing on whatever it ends up mixed into.

This is a real relational table (`containment`, see `_duckdb_schema.py`),
not a JSON blob - one row per (component, structural ancestor) pair, which
is exactly the shape Phase 7's networkx projection reads directly as
`(parent_path, child_path)` graph edges for module detection.

Details: docs/dev/database/_duckdb_containment_store.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List


class _DuckDBContainmentMixin:
    """Details: docs/dev/database/_duckdb_containment_store.md#_duckdbcontainmentmixin"""

    def record_component_ancestors(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        rows = [
            {
                "site": site, "page_url": page_url, "child_path": entry["path"],
                "parent_path": a.get("path", ""), "depth": a.get("depth", 0),
                "parent_tag": a.get("tag", ""), "parent_role": a.get("role", ""),
                "parent_landmark": a.get("landmark", ""),
                "parent_id": a.get("id", ""), "parent_class": a.get("class", ""),
            }
            for entry in entries
            for a in entry.get("ancestors") or []
        ]
        child_paths = [entry["path"] for entry in entries]

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            # Replace, not append - a component rediscovered on a later
            # pass gets its containment refreshed, not stacked with the
            # previous pass's. Scoped to exactly the components in this
            # call, not the whole page: record_inventory can run more than
            # once per page (a same-page reveal chain), each time with only
            # the newly-relevant components, and a blanket page-level wipe
            # would erase valid containment for components this call
            # doesn't happen to mention.
            if child_paths:
                conn.execute(
                    "DELETE FROM containment WHERE site = $site AND page_url = $page_url "
                    "AND child_path IN $child_paths",
                    {"site": site, "page_url": page_url, "child_paths": child_paths},
                )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO containment (site, page_url, child_path, parent_path, depth,
                                              parent_tag, parent_role, parent_landmark, parent_id, parent_class)
                    VALUES ($site, $page_url, $child_path, $parent_path, $depth,
                            $parent_tag, $parent_role, $parent_landmark, $parent_id, $parent_class)
                    """,
                    rows,
                )

        self._call(op)

    def get_containment_ledger(self, site: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        def op(conn) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
            db_rows = conn.execute(
                """
                SELECT page_url, child_path, parent_path, depth, parent_tag, parent_role, parent_landmark,
                       parent_id, parent_class
                FROM containment WHERE site = $site ORDER BY page_url, child_path, depth
                """,
                {"site": site},
            ).fetchall()
            ledger: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            for page_url, child_path, parent_path, depth, tag, role, landmark, pid, pclass in db_rows:
                ledger.setdefault(page_url, {}).setdefault(child_path, []).append(
                    {
                        "path": parent_path, "depth": depth, "tag": tag, "role": role,
                        "landmark": landmark, "id": pid, "class": pclass,
                    }
                )
            return ledger

        return self._call(op)
