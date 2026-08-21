"""Literal-row-merge collapse for `Container` - the same shape
`component_merge.py::merge_components` follows, over `Container`'s own
edges. `_LadybugContainerMergeMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Details: docs/dev/database/ladybug/container_merge.md#module
"""
from __future__ import annotations

from typing import List, Tuple


class _LadybugContainerMergeMixin:
    """Details: docs/dev/database/ladybug/container_merge.md#_ladybugcontainermergemixin"""

    def merge_containers(self, groups: List[Tuple[str, List[str]]]) -> None:
        """Collapse each `(canonical_id, [absorbed_id, ...])` group into
        one `Container` row - `HAS_CONTAINER`, and `CONTAINS` on both the
        containing and the contained side, copy onto the canonical row;
        the absorbed rows are then deleted.

        `COMPOSITE_VARIANT_OF`/`DERIVED_FROM(CompositeFamily -> Container)`
        are not handled here for the same reason `component_merge.py`
        skips `VARIANT_OF`: per #135's pipeline ordering, composite family
        grouping always runs after composite exact collapse, so neither
        edge can exist on an about-to-be-absorbed `Container` yet.
        Details: docs/dev/database/ladybug/container_merge.md#merge_containers
        """
        pairs = [
            (canonical_id, absorbed_id)
            for canonical_id, absorbed_ids in groups
            for absorbed_id in absorbed_ids
            if absorbed_id != canonical_id
        ]
        if not pairs:
            return
        rows = [{"canonical_id": c, "absorbed_id": a} for c, a in pairs]
        absorbed_ids = [a for _, a in pairs]

        def op(conn) -> None:
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (p:Page)-[e:HAS_CONTAINER]->(:Container {id: r.absorbed_id})
                MATCH (canonical:Container {id: r.canonical_id})
                MERGE (p)-[ne:HAS_CONTAINER {path: e.path}]->(canonical)
                SET ne.element_id = e.element_id
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (parent:Container)-[:CONTAINS]->(:Container {id: r.absorbed_id})
                MATCH (canonical:Container {id: r.canonical_id})
                MERGE (parent)-[:CONTAINS]->(canonical)
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (:Container {id: r.absorbed_id})-[:CONTAINS]->(child:Container)
                MATCH (canonical:Container {id: r.canonical_id})
                MERGE (canonical)-[:CONTAINS]->(child)
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (:Container {id: r.absorbed_id})-[:CONTAINS]->(child:Component)
                MATCH (canonical:Container {id: r.canonical_id})
                MERGE (canonical)-[:CONTAINS]->(child)
                """,
                {"rows": rows},
            )
            conn.execute(
                "UNWIND $ids AS id MATCH (c:Container {id: id}) DETACH DELETE c",
                {"ids": absorbed_ids},
            )

        self._call(op)
