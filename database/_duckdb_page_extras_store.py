"""Page-level "extras" CRUD for `DuckDBGraphStore` - the measurement-pass
data (accessibility violations, `:hover`/`:focus` styles, tab order) and
`<meta>`/network-load data that don't belong in the core Page/Site/edge
file, split out for the same file-size reason as every other mixin here.
`_DuckDBPageExtrasMixin` is combined into the public `DuckDBGraphStore`
class via multiple inheritance; every method here relies on
`self._call(...)`/`self._ensure_page(...)` existing on whatever it ends up
mixed into.

Unlike `network_requests` (still a JSON-TEXT blob column on `pages`, kept
that way until Phase 6 gives it a real relational schema - see
`_duckdb_schema.py`'s own comment), accessibility violations, metadata, and
measurements get real child tables here - this is the concrete "structured
information pattern" the storage migration plan exists to deliver, and
nothing here is superseded by later phases.

Details: docs/dev/database/_duckdb_page_extras_store.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


class _DuckDBPageExtrasMixin:
    """Details: docs/dev/database/_duckdb_page_extras_store.md#_duckdbpageextrasmixin"""

    def record_accessibility_violations(self, site: str, page_url: str, violations: List[Dict[str, Any]]) -> None:
        # Replace, not append (GraphStore's own contract) - delete this
        # page's prior audit before inserting the new one.
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.execute(
                "DELETE FROM accessibility_violation_nodes WHERE violation_id IN "
                "(SELECT violation_id FROM accessibility_violations WHERE site = $site AND url = $url)",
                {"site": site, "url": page_url},
            )
            conn.execute(
                "DELETE FROM accessibility_violations WHERE site = $site AND url = $url",
                {"site": site, "url": page_url},
            )
            for v in violations:
                violation_id = conn.execute(
                    """
                    INSERT INTO accessibility_violations (site, url, rule_id, impact, help, help_url, criteria, total_nodes)
                    VALUES ($site, $url, $rule_id, $impact, $help, $help_url, $criteria, $total_nodes)
                    RETURNING violation_id
                    """,
                    {
                        "site": site, "url": page_url, "rule_id": v.get("rule_id", ""),
                        "impact": v.get("impact", ""), "help": v.get("help", ""),
                        "help_url": v.get("help_url", ""), "criteria": json.dumps(v.get("criteria") or []),
                        "total_nodes": v.get("total_nodes", 0),
                    },
                ).fetchone()[0]
                nodes = [
                    {
                        "violation_id": violation_id, "path": n.get("path", ""),
                        "axe_target": n.get("axe_target", ""), "summary": n.get("summary", ""),
                    }
                    for n in v.get("nodes") or []
                ]
                if nodes:
                    conn.executemany(
                        "INSERT INTO accessibility_violation_nodes (violation_id, path, axe_target, summary) "
                        "VALUES ($violation_id, $path, $axe_target, $summary)",
                        nodes,
                    )

        self._call(op)

    def get_accessibility_violations(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        def op(conn) -> Dict[str, List[Dict[str, Any]]]:
            violations = conn.execute(
                "SELECT violation_id, url, rule_id, impact, help, help_url, criteria, total_nodes "
                "FROM accessibility_violations WHERE site = $site",
                {"site": site},
            ).fetchall()
            result: Dict[str, List[Dict[str, Any]]] = {}
            for violation_id, url, rule_id, impact, help_text, help_url, criteria, total_nodes in violations:
                nodes = conn.execute(
                    "SELECT path, axe_target, summary FROM accessibility_violation_nodes WHERE violation_id = $vid",
                    {"vid": violation_id},
                ).fetchall()
                result.setdefault(url, []).append(
                    {
                        "rule_id": rule_id, "impact": impact, "help": help_text, "help_url": help_url,
                        "criteria": json.loads(criteria), "total_nodes": total_nodes,
                        "nodes": [{"path": n[0], "axe_target": n[1], "summary": n[2]} for n in nodes],
                    }
                )
            return result

        return self._call(op)

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

    def record_page_measurements(self, site: str, page_url: str, measurements: Dict[str, Any]) -> None:
        def op(conn) -> None:
            self._ensure_page(conn, site, page_url)
            conn.execute(
                "DELETE FROM page_pseudo_styles WHERE site = $site AND url = $url", {"site": site, "url": page_url}
            )
            conn.execute(
                "DELETE FROM page_tab_order WHERE site = $site AND url = $url", {"site": site, "url": page_url}
            )
            style_rows = [
                {"site": site, "url": page_url, "path": entry.get("path", ""), "state": state, "property": prop, "value": value}
                for entry in measurements.get("pseudo_styles") or []
                for state, properties in (entry.get("states") or {}).items()
                for prop, value in properties.items()
            ]
            if style_rows:
                conn.executemany(
                    "INSERT INTO page_pseudo_styles (site, url, path, state, property, value) "
                    "VALUES ($site, $url, $path, $state, $property, $value)",
                    style_rows,
                )
            tab_rows = [
                {
                    "site": site, "url": page_url, "seq": seq,
                    "path": entry.get("path", ""), "tag": entry.get("tag", ""), "text": entry.get("text", ""),
                    "focus_visible": bool(entry.get("focus_visible", False)), "dom_index": entry.get("dom_index"),
                    "tabindex": entry.get("tabindex", ""), "offscreen": bool(entry.get("offscreen", False)),
                }
                for seq, entry in enumerate(measurements.get("tab_order") or [])
            ]
            if tab_rows:
                conn.executemany(
                    """
                    INSERT INTO page_tab_order (site, url, seq, path, tag, text, focus_visible, dom_index, tabindex, offscreen)
                    VALUES ($site, $url, $seq, $path, $tag, $text, $focus_visible, $dom_index, $tabindex, $offscreen)
                    """,
                    tab_rows,
                )

        self._call(op)

    def get_page_measurements(self, site: str) -> Dict[str, Any]:
        def op(conn) -> Dict[str, Any]:
            result: Dict[str, Any] = {}
            style_rows = conn.execute(
                "SELECT url, path, state, property, value FROM page_pseudo_styles WHERE site = $site "
                "ORDER BY url, path", {"site": site},
            ).fetchall()
            by_url_path: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for url, path, state, prop, value in style_rows:
                entry = by_url_path.setdefault((url, path), {"path": path, "states": {}})
                entry["states"].setdefault(state, {})[prop] = value
                result.setdefault(url, {}).setdefault("pseudo_styles", [])
            for (url, _path), entry in by_url_path.items():
                result[url]["pseudo_styles"].append(entry)

            tab_rows = conn.execute(
                "SELECT url, path, tag, text, focus_visible, dom_index, tabindex, offscreen "
                "FROM page_tab_order WHERE site = $site ORDER BY url, seq", {"site": site},
            ).fetchall()
            for url, path, tag, text, focus_visible, dom_index, tabindex, offscreen in tab_rows:
                result.setdefault(url, {}).setdefault("tab_order", []).append(
                    {
                        "path": path, "tag": tag, "text": text, "focus_visible": focus_visible,
                        "dom_index": dom_index, "tabindex": tabindex, "offscreen": offscreen,
                    }
                )
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
