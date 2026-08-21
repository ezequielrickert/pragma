"""Inferred-component-family write/read path for `LadybugGraphStore` -
split out for the same file-size reason the retired DuckDB backend split
`_duckdb_component_family_store.py` out on its own.
`_LadybugComponentFamilyMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Unaffected by the API-contract redesign (step 7) - a `ComponentFamily` is
still a deterministic cluster of `Component` nodes, now produced by
`analysis/component_matching_pipeline.py`'s leaf-vector clustering rather
than the retired `generators/component_family.py::build_component_families`
Jaccard pass (issue #139). Called by `Engine`'s post-crawl pass, not
`GraphStoreSink` - inferred once the whole site is in the graph, not
incrementally as the crawl proceeds.

Details: docs/dev/database/ladybug/component_family.md#module
"""
from __future__ import annotations

from typing import Dict, List

from core.interfaces import ComponentFamily
from ._component_lookup import resolve_component_ids


class _LadybugComponentFamilyMixin:
    """Details: docs/dev/database/ladybug/component_family.md#_ladybugcomponentfamilymixin"""

    def record_component_families(self, families: List[ComponentFamily]) -> None:
        """Replace the site's entire inferred-family structure with
        `families` - full rebuild, not an incremental merge, since
        cluster membership isn't guaranteed stable across runs.

        `member_paths` is `(page_url, path)`, resolved to a `Component`
        through its `HAS_COMPONENT` edge rather than a directly-constructed
        id (content-derived and page-decoupled per #134, so no id can be
        built from `(page_url, path)` alone any more). A pair that doesn't
        resolve to a real `Component` is silently skipped, matching
        `GraphStore.record_component_families`'s own documented contract.
        Details: docs/dev/database/ladybug/component_family.md#record_component_families
        """
        def op(conn) -> None:
            # Full rebuild - clear every existing family before writing
            # the new set.
            conn.execute("MATCH (f:ComponentFamily) DETACH DELETE f")
            rows = []
            for family in families:
                by_page: Dict[str, List[str]] = {}
                for page_url, path in family.member_paths:
                    by_page.setdefault(page_url, []).append(path)
                member_ids = [
                    component_id
                    for page_url, paths in by_page.items()
                    for component_id in resolve_component_ids(conn, page_url, paths).values()
                ]
                rows.append({
                    "tag": family.tag, "component_type": family.component_type,
                    "common_classes": list(family.common_classes), "purpose": family.purpose,
                    "members": member_ids,
                })
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

        `member_paths` is expanded through each member's `HAS_COMPONENT`
        edges, not decoded from its id (content-derived and page-decoupled
        per #134, so it no longer encodes a page) - a canonical member
        shared by several pages now legitimately contributes one
        `(page_url, path)` pair per page, not a single one as before.

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
                MATCH (page:Page)-[e:HAS_COMPONENT]->(c)
                WITH f, collect(DISTINCT [page.url, e.path]) AS member_paths
                RETURN f.tag, f.component_type, f.common_classes, f.purpose, member_paths
                """
            )
            families = []
            for tag, component_type, common_classes, purpose, member_paths in rows:
                members = tuple(sorted((page_url, path) for page_url, path in member_paths))
                families.append(
                    ComponentFamily(
                        tag=tag, component_type=component_type,
                        common_classes=tuple(common_classes),
                        member_paths=members, purpose=purpose or "",
                    )
                )
            return families

        return self._call(op)
