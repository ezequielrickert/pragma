"""Inferred-composite-family write/read path for `LadybugGraphStore` -
`CompositeFamily`'s counterpart to `component_family.py`'s
`ComponentFamily` handling, same shape, one level up. `_LadybugComposite
FamilyMixin` is combined into the public `LadybugGraphStore` class via
multiple inheritance and relies on `self._call(...)` existing on whatever
it ends up mixed into.

Details: docs/dev/database/ladybug/composite_family.md#module
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from core.interfaces import CompositeFamily


def _resolve_container_ids(conn, page_url: str, paths: Iterable[str]) -> Dict[str, str]:
    """`{path: container_id}` for every given path with a `HAS_CONTAINER`
    edge on this page already - `_component_lookup.py::resolve_component_ids`'s
    counterpart for `Container`, kept local rather than shared since this
    is its only caller.
    Details: docs/dev/database/ladybug/composite_family.md#_resolve_container_ids
    """
    paths = list(paths)
    if not paths:
        return {}
    rows = conn.execute(
        """
        MATCH (page:Page {url: $page_url})-[e:HAS_CONTAINER]->(n:Container)
        WHERE e.path IN $paths
        RETURN e.path, n.id
        """,
        {"page_url": page_url, "paths": paths},
    )
    return {path: container_id for path, container_id in rows}


class _LadybugCompositeFamilyMixin:
    """Details: docs/dev/database/ladybug/composite_family.md#_ladybugcompositefamilymixin"""

    def record_composite_families(self, families: List[CompositeFamily]) -> None:
        """Replace the site's entire inferred-composite-family structure
        with `families` - full rebuild, same contract as
        `record_component_families`. `member_paths` is `(page_url, path)`,
        resolved to a `Container` through its `HAS_CONTAINER` edge; a pair
        that doesn't resolve to a real `Container` is silently skipped.
        Details: docs/dev/database/ladybug/composite_family.md#record_composite_families
        """
        def op(conn) -> None:
            conn.execute("MATCH (f:CompositeFamily) DETACH DELETE f")
            rows = []
            for family in families:
                by_page: Dict[str, List[str]] = {}
                for page_url, path in family.member_paths:
                    by_page.setdefault(page_url, []).append(path)
                member_ids = [
                    container_id
                    for page_url, paths in by_page.items()
                    for container_id in _resolve_container_ids(conn, page_url, paths).values()
                ]
                rows.append({"root_tag": family.root_tag, "purpose": family.purpose, "members": member_ids})
            if not rows:
                return
            conn.execute(
                """
                UNWIND $rows AS r
                CREATE (f:CompositeFamily {root_tag: r.root_tag, purpose: r.purpose})
                WITH f, r.members AS member_ids
                UNWIND member_ids AS member_id
                MATCH (n:Container {id: member_id})
                CREATE (n)-[:COMPOSITE_VARIANT_OF]->(f)
                """,
                {"rows": rows},
            )

        self._call(op)

    def get_composite_families(self) -> List[CompositeFamily]:
        """Every inferred composite family currently recorded for the
        site - same shape/reasoning as `get_component_families`, over
        `COMPOSITE_VARIANT_OF`/`HAS_CONTAINER` instead of
        `VARIANT_OF`/`HAS_COMPONENT`.
        Details: docs/dev/database/ladybug/composite_family.md#get_composite_families
        """
        def op(conn) -> List[CompositeFamily]:
            rows = conn.execute(
                """
                MATCH (n:Container)-[:COMPOSITE_VARIANT_OF]->(f:CompositeFamily)
                MATCH (page:Page)-[e:HAS_CONTAINER]->(n)
                WITH f, collect(DISTINCT [page.url, e.path]) AS member_paths
                RETURN f.root_tag, f.purpose, member_paths
                """
            )
            families = []
            for root_tag, purpose, member_paths in rows:
                members = tuple(sorted((page_url, path) for page_url, path in member_paths))
                families.append(CompositeFamily(root_tag=root_tag, member_paths=members, purpose=purpose or ""))
            return families

        return self._call(op)
