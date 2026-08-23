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

from typing import Dict, List, Tuple

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

        `family.subgroups` (issue #171) is written as an `int` `subgroup`
        property on each member's `VARIANT_OF` edge - its index into
        `subgroups` - rather than as a property on the `ComponentFamily`
        node itself: a nested list-of-lists doesn't fit a Kùzu column, and
        a sub-cluster is inherently a per-membership fact anyway (which
        group *this* component landed in), the same shape `HAS_OPTION`'s
        `seq` property already uses for a per-edge ordinal. A member
        absent from every subgroup (an empty/unset `subgroups`) gets the
        column's own default, `0`.
        Details: docs/dev/database/ladybug/component_family.md#record_component_families
        """
        def op(conn) -> None:
            # Full rebuild - clear every existing family before writing
            # the new set.
            conn.execute("MATCH (f:ComponentFamily) DETACH DELETE f")
            rows = []
            for family in families:
                subgroup_of = {
                    member_path: index
                    for index, subgroup in enumerate(family.subgroups)
                    for member_path in subgroup
                }
                by_page: Dict[str, List[str]] = {}
                for page_url, path in family.member_paths:
                    by_page.setdefault(page_url, []).append(path)
                members = [
                    {"id": component_id, "subgroup": subgroup_of.get((page_url, path), 0)}
                    for page_url, paths in by_page.items()
                    for path, component_id in resolve_component_ids(conn, page_url, paths).items()
                ]
                rows.append({
                    "tag": family.tag, "component_type": family.component_type,
                    "common_classes": list(family.common_classes), "purpose": family.purpose,
                    "members": members,
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
                WITH f, r.members AS members
                UNWIND members AS m
                MATCH (c:Component {id: m.id})
                CREATE (c)-[:VARIANT_OF {subgroup: m.subgroup}]->(f)
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

        `subgroups` is rebuilt by re-grouping each member's `VARIANT_OF.
        subgroup` int (issue #171) - the inverse of how `record_component_
        families` wrote it. A family recorded before that field existed
        (or by a caller that never ran the sub-cluster pass) has every
        edge at the column default, `0`, which comes back as one
        subgroup holding every member - a reasonable reading of "no
        finer split known", not a lossy round-trip: nothing this store
        ever wrote as `()` distinguishably becomes `()` again, since an
        unpartitioned family and a family with exactly one partition
        mean the same thing to a reader either way. `v.subgroup` is
        `CAST` to `STRING` inside the query - Kùzu's `LIST` needs one
        element type throughout, and this list already mixes in two
        `STRING` columns (`page.url`, `e.path`).
        Details: docs/dev/database/ladybug/component_family.md#get_component_families
        """
        def op(conn) -> List[ComponentFamily]:
            rows = conn.execute(
                """
                MATCH (c:Component)-[v:VARIANT_OF]->(f:ComponentFamily)
                MATCH (page:Page)-[e:HAS_COMPONENT]->(c)
                WITH f, collect(DISTINCT [page.url, e.path, CAST(v.subgroup AS STRING)]) AS member_rows
                RETURN f.tag, f.component_type, f.common_classes, f.purpose, member_rows
                """
            )
            families = []
            for tag, component_type, common_classes, purpose, member_rows in rows:
                members = tuple(sorted((page_url, path) for page_url, path, _ in member_rows))
                by_subgroup: Dict[int, List[Tuple[str, str]]] = {}
                for page_url, path, subgroup in member_rows:
                    by_subgroup.setdefault(int(subgroup), []).append((page_url, path))
                subgroups = tuple(sorted(
                    (tuple(sorted(set(paths))) for paths in by_subgroup.values()),
                    key=lambda group: (-len(group), group),
                ))
                families.append(
                    ComponentFamily(
                        tag=tag, component_type=component_type,
                        common_classes=tuple(common_classes),
                        member_paths=members, purpose=purpose or "",
                        subgroups=subgroups,
                    )
                )
            return families

        return self._call(op)
