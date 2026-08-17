"""Container/CONTAINS write path for `LadybugGraphStore` - storage-
migration plan step 8. `_LadybugContainmentMixin` is combined into the
public `LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Direct containment only, matching `Container`'s own schema comment - the
retired DuckDB backend's `containment` table stored the full transitive
closure (one row per (component, ancestor) pair at every depth, 58,714
rows in the snapshot that shaped this plan, 2.1 per component). Here,
`discover_components.js::structuralAncestorsOf`'s per-component list
(nearest ancestor first) becomes one direct edge per consecutive pair -
`CONTAINS*1..n` recovers the full chain by traversal, which is what
makes storing only the direct edges correct rather than a data loss.

No read method is ported: `get_containment_ledger` had zero production
callers in the retired backend (confirmed in the storage-migration plan's
own old-schema audit), so there is nothing to keep working here - a named
query with a real caller replaces it in a later step, per the plan's
retrieval-surface section.

Details: docs/dev/database/ladybug/containment.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

from .ids import component_id


class _LadybugContainmentMixin:
    """Details: docs/dev/database/ladybug/containment.md#_ladybugcontainmentmixin"""

    def record_component_ancestors(self, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """`entries`: one `{"path": component_path, "ancestors": [...]}`
        per component, `ancestors` ordered nearest-first
        (`structuralAncestorsOf`'s own contract) - exactly what
        `GraphStoreSink.record_inventory` already assembles, after its
        own `record_components` batch, so the `Component` row this
        `CONTAINS` chain terminates at normally exists already. The leaf
        edge still `MERGE`s the `Component` (never a plain `MATCH`)
        rather than depend on that ordering: confirmed against the real
        engine, a `MATCH` that matches nothing drops the *entire* pattern
        silently, not just that one clause - a batch running before the
        component row exists would otherwise lose every containment edge
        with no error at all.
        Details: docs/dev/database/ladybug/containment.md#record_component_ancestors
        """
        containers: Dict[str, Dict[str, Any]] = {}
        container_edges: List[Dict[str, str]] = []
        component_edges: List[Dict[str, str]] = []

        for entry in entries:
            comp_path = entry.get("path")
            ancestors = entry.get("ancestors") or []
            if not comp_path or not ancestors:
                continue
            chain_ids = []
            for ancestor in ancestors:
                ancestor_path = ancestor.get("path")
                if not ancestor_path:
                    continue
                container_id = component_id(page_url, ancestor_path)
                containers[container_id] = {
                    "id": container_id, "path": ancestor_path, "tag": ancestor.get("tag", ""),
                    "role": ancestor.get("role", ""), "landmark": ancestor.get("landmark", ""),
                    "element_id": ancestor.get("id", ""), "css_class": ancestor.get("class", ""),
                }
                chain_ids.append(container_id)
            if not chain_ids:
                continue
            # Each container directly contains only the one nearer to the
            # leaf than itself - structuralAncestorsOf's nearest-first
            # order makes consecutive pairs exactly the direct edges.
            for nearer, further in zip(chain_ids, chain_ids[1:]):
                container_edges.append({"from_id": further, "to_id": nearer})
            component_edges.append(
                {"container_id": chain_ids[0], "component_id": component_id(page_url, comp_path)}
            )

        if not containers:
            return

        def op(conn) -> None:
            conn.execute(
                """
                UNWIND $containers AS c
                MERGE (n:Container {id: c.id})
                SET n.path = c.path, n.tag = c.tag, n.role = c.role, n.landmark = c.landmark,
                    n.element_id = c.element_id, n.css_class = c.css_class
                """,
                {"containers": list(containers.values())},
            )
            if container_edges:
                conn.execute(
                    """
                    UNWIND $edges AS e
                    MATCH (parent:Container {id: e.from_id}), (child:Container {id: e.to_id})
                    MERGE (parent)-[:CONTAINS]->(child)
                    """,
                    {"edges": container_edges},
                )
            if component_edges:
                conn.execute(
                    """
                    UNWIND $edges AS e
                    MATCH (parent:Container {id: e.container_id})
                    MERGE (child:Component {id: e.component_id})
                    MERGE (parent)-[:CONTAINS]->(child)
                    """,
                    {"edges": component_edges},
                )

        self._call(op)
