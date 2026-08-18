"""Inferred-component-family write/read path for `LadybugGraphStore` -
split out for the same file-size reason the retired DuckDB backend split
`_duckdb_component_family_store.py` out on its own.
`_LadybugComponentFamilyMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Unaffected by the API-contract redesign (step 7) - a `ComponentFamily` is
still a deterministic cluster of `Component` nodes, the same shape
`generators/component_family.py::build_component_families` has always
produced. Called by `Engine`'s post-crawl pass, not `GraphStoreSink` -
inferred once the whole site is in the graph, not incrementally as the
crawl proceeds.

Details: docs/dev/database/ladybug/component_family.md#module
"""
from __future__ import annotations

from typing import List

from core.interfaces import ComponentFamily


class _LadybugComponentFamilyMixin:
    """Details: docs/dev/database/ladybug/component_family.md#_ladybugcomponentfamilymixin"""

    def record_component_families(self, families: List[ComponentFamily]) -> None:
        """Replace the site's entire inferred-family structure with
        `families` - full rebuild, not an incremental merge, since
        cluster membership isn't guaranteed stable across runs.

        A `member_paths` entry that doesn't resolve to a real `Component`
        is silently skipped, matching `GraphStore.record_component_families`'s
        own documented contract - confirmed the real engine does this
        (a `MATCH` inside an `UNWIND` drops that iteration, not the
        whole write) rather than assumed.
        Details: docs/dev/database/ladybug/component_family.md#record_component_families
        """
        rows = [
            {
                "tag": family.tag, "component_type": family.component_type,
                "common_classes": list(family.common_classes), "purpose": family.purpose,
                "members": [f"{page_url}|{path}" for page_url, path in family.member_paths],
            }
            for family in families
        ]

        def op(conn) -> None:
            # Full rebuild - clear every existing family before writing
            # the new set.
            conn.execute("MATCH (f:ComponentFamily) DETACH DELETE f")
            if not rows:
                return
            conn.execute(
                """
                UNWIND $rows AS r
                CREATE (f:ComponentFamily {
                    tag: r.tag, component_type: r.component_type,
                    common_classes: r.common_classes, purpose: r.purpose
                })
                WITH f, r.members AS member_ids
                UNWIND member_ids AS member_id
                MATCH (c:Component {id: member_id})
                CREATE (c)-[:VARIANT_OF]->(f)
                """,
                {"rows": rows},
            )

        self._call(op)

    def get_component_families(self) -> List[ComponentFamily]:
        """Every inferred family currently recorded for the site. A
        family with zero resolved members is excluded, matching the
        retired DuckDB backend's own behavior - the `MATCH` here requires
        at least one `VARIANT_OF` edge to produce a row at all.

        Grouped by `f` itself inside the query (`WITH f, collect(...)`),
        not by a Python-side key: `id(f)` comes back as an unhashable
        dict (`{"table": ..., "offset": ...}`), confirmed against the
        real engine, so two families that happen to share every property
        would silently collapse into one under a naive `dict.setdefault`
        keyed by that value. Cypher's own grouping has no such problem -
        it distinguishes two nodes by identity regardless of whether
        their properties are identical.
        Details: docs/dev/database/ladybug/component_family.md#get_component_families
        """
        def op(conn) -> List[ComponentFamily]:
            rows = conn.execute(
                """
                MATCH (c:Component)-[:VARIANT_OF]->(f:ComponentFamily)
                WITH f, collect(c.id) AS member_ids
                RETURN f.tag, f.component_type, f.common_classes, f.purpose, member_ids
                """
            )
            families = []
            for tag, component_type, common_classes, purpose, member_ids in rows:
                members = tuple(sorted(tuple(mid.partition("|")[::2]) for mid in member_ids))
                families.append(
                    ComponentFamily(
                        tag=tag, component_type=component_type,
                        common_classes=tuple(common_classes),
                        member_paths=members, purpose=purpose or "",
                    )
                )
            return families

        return self._call(op)
