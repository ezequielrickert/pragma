"""Inferred component-family CRUD for `DuckDBGraphStore` - mirrors
`neo4j_component_family_store.py`'s role. `_DuckDBComponentFamilyMixin` is
combined into the public `DuckDBGraphStore` class via multiple
inheritance; every method here relies on `self._call(...)` existing on
whatever it ends up mixed into.

`apply_tag_labels` is deliberately not overridden here - `GraphStore`'s own
default is a no-op (`core/interfaces.py`), the same "no browser to color"
reasoning `InMemoryGraphStore` relies on applies to an embedded columnar
store too.

Details: docs/dev/database/_duckdb_component_family_store.md#module
"""
from __future__ import annotations

import json
from typing import List

from core.interfaces import ComponentFamily


class _DuckDBComponentFamilyMixin:
    """Details: docs/dev/database/_duckdb_component_family_store.md#_duckdbcomponentfamilymixin"""

    def record_component_families(self, site: str, families: List[ComponentFamily]) -> None:
        def op(conn) -> None:
            # Full rebuild, not an incremental merge - cluster membership
            # isn't kept stable across runs (see GraphStore's own docstring).
            conn.execute(
                "DELETE FROM component_family_members WHERE family_id IN "
                "(SELECT family_id FROM component_families WHERE site = $site)",
                {"site": site},
            )
            conn.execute("DELETE FROM component_families WHERE site = $site", {"site": site})
            for family in families:
                family_id = conn.execute(
                    """
                    INSERT INTO component_families (site, tag, component_type, common_classes, purpose)
                    VALUES ($site, $tag, $component_type, $common_classes, $purpose)
                    RETURNING family_id
                    """,
                    {
                        "site": site, "tag": family.tag, "component_type": family.component_type,
                        "common_classes": json.dumps(list(family.common_classes)), "purpose": family.purpose,
                    },
                ).fetchone()[0]
                # A member_paths entry that doesn't resolve to a real
                # Component is silently skipped - same as Neo4j's MATCH
                # producing no row for that UNWIND entry - rather than
                # raising, matching GraphStore.record_component_families'
                # own documented contract.
                for page_url, path in family.member_paths:
                    exists = conn.execute(
                        "SELECT 1 FROM components WHERE site = $site AND page_url = $page_url AND path = $path",
                        {"site": site, "page_url": page_url, "path": path},
                    ).fetchone()
                    if exists:
                        conn.execute(
                            "INSERT INTO component_family_members (family_id, page_url, path) "
                            "VALUES ($family_id, $page_url, $path)",
                            {"family_id": family_id, "page_url": page_url, "path": path},
                        )

        self._call(op)

    def get_component_families(self, site: str) -> List[ComponentFamily]:
        def op(conn) -> List[ComponentFamily]:
            families = conn.execute(
                "SELECT family_id, tag, component_type, common_classes, purpose "
                "FROM component_families WHERE site = $site",
                {"site": site},
            ).fetchall()
            result: List[ComponentFamily] = []
            for family_id, tag, component_type, common_classes_json, purpose in families:
                members = conn.execute(
                    "SELECT page_url, path FROM component_family_members WHERE family_id = $family_id "
                    "ORDER BY page_url, path",
                    {"family_id": family_id},
                ).fetchall()
                # A family with zero resolved members is excluded, matching
                # Neo4j's MATCH-requires-the-edge-to-exist behavior.
                if not members:
                    continue
                result.append(
                    ComponentFamily(
                        tag=tag, component_type=component_type,
                        common_classes=tuple(json.loads(common_classes_json)),
                        member_paths=tuple((m[0], m[1]) for m in members),
                        purpose=purpose or "",
                    )
                )
            return result

        return self._call(op)
