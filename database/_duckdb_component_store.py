"""Component CRUD for `DuckDBGraphStore` - split out to mirror
`neo4j_component_store.py`'s role and stay under this project's file-size
threshold. `_DuckDBComponentMixin` is combined into the public
`DuckDBGraphStore` class via multiple inheritance; every method here
relies on `self._call(...)` existing on whatever it ends up mixed into.
Details: docs/dev/database/_duckdb_component_store.md#module
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import ComponentFacts, VisitStep
from ._duckdb_schema import DESCRIPTIVE_COLUMNS, DESCRIPTIVE_UPDATE_SET, FACTS_FIELDS

_INSERT_COLUMNS = ("site", "page_url", "path") + DESCRIPTIVE_COLUMNS
_INSERT_PLACEHOLDERS = ", ".join(f"${col}" for col in _INSERT_COLUMNS)
_INSERT_COLUMN_LIST = ", ".join(_INSERT_COLUMNS)


class _DuckDBComponentMixin:
    """Details: docs/dev/database/_duckdb_component_store.md#_duckdbcomponentmixin"""

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
        params = {
            "site": site, "page_url": page_url, "path": path,
            "tag": tag, "text": text, "role": role, "input_type": input_type,
            "visible": visible, "layer": layer, "x": x, "y": y, "width": width, "height": height,
            "component_type": component_type,
            **asdict(facts or ComponentFacts()),
        }

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.execute(
                f"""
                INSERT INTO components ({_INSERT_COLUMN_LIST})
                VALUES ({_INSERT_PLACEHOLDERS})
                ON CONFLICT (site, page_url, path) DO UPDATE SET {DESCRIPTIVE_UPDATE_SET}
                """,
                params,
            )

        self._call(op)

    def record_components(self, site: str, page_url: str, components: List[Dict[str, Any]]) -> None:
        """Batched `record_component`: one `executemany` for a whole
        discovery pass's components instead of one round-trip each -
        collapses the 100-300+ individual writes a component-heavy real
        page produced, same motivation as Neo4j's UNWIND version.
        """
        if not components:
            return
        rows = [
            {
                "site": site, "page_url": page_url, "path": item["path"],
                "tag": item.get("tag", ""), "text": item.get("text", ""),
                "role": item.get("role", ""), "input_type": item.get("input_type", ""),
                "visible": item.get("visible", True), "layer": item.get("layer", "semantic"),
                "x": item.get("x"), "y": item.get("y"),
                "width": item.get("width"), "height": item.get("height"),
                "component_type": item.get("component_type", ""),
                **asdict(item.get("facts") or ComponentFacts()),
            }
            for item in components
        ]

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.executemany(
                f"""
                INSERT INTO components ({_INSERT_COLUMN_LIST})
                VALUES ({_INSERT_PLACEHOLDERS})
                ON CONFLICT (site, page_url, path) DO UPDATE SET {DESCRIPTIVE_UPDATE_SET}
                """,
                rows,
            )

        self._call(op)

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
        # didn't points back at its own page - same "every interaction is a
        # traversable fact, never a dangling reference" rule Neo4j's
        # :INTERACTED edges follow.
        target_url = resulting_url or page_url
        navigated = bool(resulting_url) and resulting_url != page_url
        created_at = datetime.now(timezone.utc).isoformat()
        visit_id = step.visit_id if step else ""
        step_seq = step.seq if step else 0

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            self._ensure_page(conn, site, target_url)
            _ensure_component_stub(conn, site, page_url, path)
            row = conn.execute(
                """
                UPDATE components SET interacted = TRUE, interaction_count = interaction_count + 1
                WHERE site = $site AND page_url = $page_url AND path = $path
                RETURNING interaction_count
                """,
                {"site": site, "page_url": page_url, "path": path},
            ).fetchone()
            seq = row[0]
            conn.execute(
                """
                INSERT INTO interactions (site, page_url, path, action, value, resulting_url,
                                           source_path, navigated, seq, created_at, visit_id, step_seq)
                VALUES ($site, $page_url, $path, $action, $value, $resulting_url,
                        $source_path, $navigated, $seq, $created_at, $visit_id, $step_seq)
                """,
                {
                    "site": site, "page_url": page_url, "path": path, "action": action, "value": value,
                    "resulting_url": resulting_url, "source_path": source_path, "navigated": navigated,
                    "seq": seq, "created_at": created_at, "visit_id": visit_id, "step_seq": step_seq,
                },
            )

        self._call(op)

    def record_component_options(
        self, site: str, page_url: str, path: str, options: str, option_labels: Optional[List[str]] = None
    ) -> None:
        labels_json = json.dumps(option_labels or [])

        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            _ensure_component_stub(conn, site, page_url, path)
            conn.execute(
                "UPDATE components SET options = $options, option_labels = $labels "
                "WHERE site = $site AND page_url = $page_url AND path = $path",
                {"site": site, "page_url": page_url, "path": path, "options": options, "labels": labels_json},
            )

        self._call(op)

    def record_component_network(self, site: str, page_url: str, path: str, requests_json: str) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            _ensure_component_stub(conn, site, page_url, path)
            existing = conn.execute(
                "SELECT network_requests FROM components WHERE site = $site AND page_url = $page_url AND path = $path",
                {"site": site, "page_url": page_url, "path": path},
            ).fetchone()
            batch = json.loads(existing[0]) if existing and existing[0] else []
            batch.extend(json.loads(requests_json))
            conn.execute(
                "UPDATE components SET network_requests = $entry "
                "WHERE site = $site AND page_url = $page_url AND path = $path",
                {"site": site, "page_url": page_url, "path": path, "entry": json.dumps(batch)},
            )

        self._call(op)

    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        def op(conn) -> Dict[str, Dict[str, Any]]:
            return _fetch_components(conn, "site = $site AND page_url = $page_url", {"site": site, "page_url": page_url})

        rows = self._call(op)
        return {path: record for path, (_, record) in rows.items()}

    def count_unexplored_components(self, site: str, semantic_only: bool = True) -> Tuple[int, int]:
        clause = "site = $site" + (" AND layer <> 'pointer'" if semantic_only else "")

        def op(conn) -> Tuple[int, int]:
            row = conn.execute(
                f"SELECT sum(CASE WHEN interacted THEN 0 ELSE 1 END), count(*) FROM components WHERE {clause}",
                {"site": site},
            ).fetchone()
            return (row[0] or 0, row[1] or 0)

        return self._call(op)

    def get_pages_with_unexplored_components(
        self, site: str, limit: Optional[int] = None, semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        clause = "site = $site AND interacted = FALSE" + (" AND layer <> 'pointer'" if semantic_only else "")
        limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""

        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                f"""
                SELECT page_url, count(*) AS unexplored_count FROM components WHERE {clause}
                GROUP BY page_url ORDER BY unexplored_count DESC{limit_sql}
                """,
                {"site": site},
            ).fetchall()
            return [{"url": r[0], "unexplored_count": r[1]} for r in rows]

        return self._call(op)

    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        clause = "site = $site AND page_url = $url AND interacted = FALSE"
        clause += " AND layer <> 'pointer'" if semantic_only else ""

        def op(conn) -> bool:
            row = conn.execute(f"SELECT 1 FROM components WHERE {clause} LIMIT 1", {"site": site, "url": url}).fetchone()
            return row is not None

        return self._call(op)

    def get_component_ledger(self, site: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        def op(conn) -> Dict[str, Dict[str, Dict[str, Any]]]:
            components = _fetch_components(conn, "site = $site", {"site": site})
            interactions_by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for row in conn.execute(
                """
                SELECT page_url, path, action, value, resulting_url, source_path, visit_id, step_seq
                FROM interactions WHERE site = $site ORDER BY page_url, path, seq
                """,
                {"site": site},
            ).fetchall():
                key = (row[0], row[1])
                interactions_by_key.setdefault(key, []).append(
                    {
                        "action": row[2], "value": row[3], "resulting_url": row[4],
                        "source_path": row[5], "visit_id": row[6], "step_seq": row[7],
                    }
                )

            ledger: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for path, (page_url, record) in components.items():
                record["interactions"] = interactions_by_key.get((page_url, path), [])
                ledger.setdefault(page_url, {})[path] = record
            return ledger

        return self._call(op)


_FIXED_COLUMNS: Tuple[str, ...] = (
    "page_url", "path", "tag", "text", "role", "input_type", "visible", "layer", "interacted",
    "x", "y", "width", "height", "component_type", "options", "option_labels", "network_requests",
)


def _ensure_component_stub(conn, site: str, page_url: str, path: str) -> None:
    """Create a blank Component row if `(site, page_url, path)` doesn't
    exist yet - shared by every write method that isn't `record_component`/
    `record_components` itself (which own the full descriptive INSERT).
    The table's own column defaults (`_duckdb_schema.py`) supply every
    blank value, the same role `_COMPONENT_BLANK_STUB` plays in the Neo4j
    backend, so there's no separate stub fragment to keep in sync here.
    """
    conn.execute(
        "INSERT INTO components (site, page_url, path) VALUES ($site, $page_url, $path) "
        "ON CONFLICT (site, page_url, path) DO NOTHING",
        {"site": site, "page_url": page_url, "path": path},
    )


def _fetch_components(conn, where: str, params: Dict[str, Any]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    """Shared by `get_component_states`/`get_component_ledger`: same SELECT,
    same result-dict assembly, keyed by `path` -> `(page_url, record)` so
    the whole-site caller (`get_component_ledger`, no `page_url` filter)
    can still group by page after the fact.
    """
    columns = ", ".join(_FIXED_COLUMNS + FACTS_FIELDS)
    rows = conn.execute(f"SELECT {columns} FROM components WHERE {where}", params).fetchall()
    result: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for row in rows:
        page_url, path = row[0], row[1]
        facts = dict(zip(FACTS_FIELDS, row[len(_FIXED_COLUMNS):]))
        result[path] = (
            page_url,
            {
                "tag": row[2], "text": row[3], "role": row[4] or "", "input_type": row[5] or "",
                "visible": row[6] if row[6] is not None else True, "layer": row[7] or "semantic",
                "interacted": row[8],
                "x": row[9], "y": row[10], "width": row[11], "height": row[12],
                "component_type": row[13] or "", "options": row[14] or "",
                "option_labels": json.loads(row[15]) if row[15] else [],
                "network_requests": json.loads(row[16]) if row[16] else [],
                **facts,
            },
        )
    return result
