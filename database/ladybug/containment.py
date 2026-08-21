"""Container/CONTAINS write path for `LadybugGraphStore` - storage-
migration plan step 8, extended by the canonical-schema migration (issue
#134). `_LadybugContainmentMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Direct containment only, matching `Container`'s own schema comment - the
retired DuckDB backend's `containment` table stored the full transitive
closure (one row per (component, ancestor) pair at every depth, 58,714
rows in the snapshot that shaped this plan, 2.1 per component). Here,
`discover_components.js::structuralAncestorsOf`'s per-component list
(nearest ancestor first) becomes one direct edge per consecutive pair -
`CONTAINS*1..n` recovers the full chain by traversal, which is what
makes storing only the direct edges correct rather than a data loss.

`Container.id` is content-derived and page-decoupled, same scheme as
`Component.id` - two ancestors with identical `tag`/`role`/`landmark`/
`css_class` `MERGE` onto one row regardless of which page discovered
them. `path`/`element_id` moved off the node onto `HAS_CONTAINER`
(new - #134's design gives every page an explicit edge to the composites
it renders, which nothing wrote before this).

No read method is ported: `get_containment_ledger` had zero production
callers in the retired backend (confirmed in the storage-migration plan's
own old-schema audit), so there is nothing to keep working here - a named
query with a real caller replaces it in a later step, per the plan's
retrieval-surface section.

Details: docs/dev/database/ladybug/containment.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._component_lookup import resolve_component_ids, stub_component_id
from .ids import container_content_id


def _container_fields(ancestor: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tag": ancestor.get("tag", ""), "role": ancestor.get("role", ""),
        "landmark": ancestor.get("landmark", ""), "css_class": ancestor.get("class", ""),
    }


class _LadybugContainmentMixin:
    """Details: docs/dev/database/ladybug/containment.md#_ladybugcontainmentmixin"""

    def record_component_ancestors(self, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """`entries`: one `{"path": component_path, "ancestors": [...]}`
        per component, `ancestors` ordered nearest-first
        (`structuralAncestorsOf`'s own contract) - exactly what
        `GraphStoreSink.record_inventory` already assembles, after its
        own `record_components` batch, so the leaf `Component` row this
        `CONTAINS` chain terminates at normally already has a
        `HAS_COMPONENT` edge to resolve through
        (`_component_lookup.resolve_component_ids`). The leaf edge still
        falls back to the shared blank-content id rather than depend on
        that ordering: confirmed against the real engine, a `MATCH` that
        matches nothing drops the *entire* pattern silently, not just
        that one clause - a batch running before the component row exists
        would otherwise lose every containment edge with no error at all.
        Details: docs/dev/database/ladybug/containment.md#record_component_ancestors
        """
        containers: Dict[str, Dict[str, Any]] = {}
        # `HAS_CONTAINER`: one row per (container, ancestor) pair on this
        # page - every ancestor of every component entry sits on this
        # page, regardless of whether it directly contains a component or
        # only another container.
        page_container_edges: List[Dict[str, str]] = []
        container_edges: List[Dict[str, str]] = []
        leaf_edges: List[Dict[str, str]] = []

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
                fields = _container_fields(ancestor)
                container_id = container_content_id(fields)
                containers[container_id] = {"id": container_id, **fields}
                page_container_edges.append({
                    "container_id": container_id, "path": ancestor_path,
                    "element_id": ancestor.get("id", ""),
                })
                chain_ids.append(container_id)
            if not chain_ids:
                continue
            # Each container directly contains only the one nearer to the
            # leaf than itself - structuralAncestorsOf's nearest-first
            # order makes consecutive pairs exactly the direct edges.
            for nearer, further in zip(chain_ids, chain_ids[1:]):
                container_edges.append({"from_id": further, "to_id": nearer})
            leaf_edges.append({"container_id": chain_ids[0], "leaf_path": comp_path})

        if not containers:
            return

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            conn.execute(
                """
                UNWIND $containers AS c
                MERGE (n:Container {id: c.id})
                SET n.tag = c.tag, n.role = c.role, n.landmark = c.landmark, n.css_class = c.css_class
                """,
                {"containers": list(containers.values())},
            )
            conn.execute(
                """
                UNWIND $edges AS e
                MATCH (page:Page {url: $page_url})
                MATCH (n:Container {id: e.container_id})
                MERGE (page)-[hc:HAS_CONTAINER {path: e.path}]->(n)
                SET hc.element_id = e.element_id
                """,
                {"edges": page_container_edges, "page_url": page_url},
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
            if leaf_edges:
                resolved = resolve_component_ids(conn, page_url, (e["leaf_path"] for e in leaf_edges))
                resolved_leaf_edges = [
                    {
                        "container_id": edge["container_id"], "leaf_path": edge["leaf_path"],
                        "component_id": resolved.get(edge["leaf_path"])
                            or stub_component_id(page_url, edge["leaf_path"]),
                    }
                    for edge in leaf_edges
                ]
                conn.execute(
                    """
                    UNWIND $edges AS e
                    MATCH (parent:Container {id: e.container_id})
                    MATCH (page:Page {url: $page_url})
                    MERGE (child:Component {id: e.component_id})
                    MERGE (page)-[:HAS_COMPONENT {path: e.leaf_path}]->(child)
                    MERGE (parent)-[:CONTAINS]->(child)
                    """,
                    {"edges": resolved_leaf_edges, "page_url": page_url},
                )

        self._call(op)

    def get_component_regions(self) -> Dict[str, Dict[str, str]]:
        """Which landmark region each component sits in -
        `{page_url: {component_path: landmark}}`.

        The question D5 asks of containment: not the whole ancestor chain,
        but the one region a reader would name ("this button is in the
        navigation"). A component's *nearest* landmark ancestor wins, so a
        `<form>` inside `<main>` reports `main` and a search box inside
        `<nav>` inside `<main>` reports `navigation` - the inner region is
        the informative one.

        Nearest is resolved by `length()` on the recursive relationship,
        confirmed against the real engine: `size()` rejects a
        `RECURSIVE_REL` outright ("Function SIZE did not receive correct
        arguments"), and `length()` is the one that takes it. With
        `ORDER BY` on that length the first row per component is already
        the nearest, so no second pass and no per-component query.

        Returns:
            One entry per page that has at least one component inside a
            landmark, and within it one entry per such component.
            Components in no landmark region at all are absent rather than
            present-with-`""`: a caller asking "which region is this in"
            gets the same "no answer" from a missing key as it would from
            an empty string, and the missing key cannot be mistaken for a
            region named `""`.

            `{}` when nothing recorded ancestry - which is also what a
            crawl from before containment capture existed reads back as.
        Details: docs/dev/database/ladybug/containment.md#get_component_regions
        """
        def op(conn) -> Dict[str, Dict[str, str]]:
            rows = conn.execute(
                """
                MATCH (p:Page)-[e:HAS_COMPONENT]->(comp:Component)
                MATCH (region:Container)-[chain:CONTAINS*1..8]->(comp)
                WHERE region.landmark <> ''
                RETURN p.url, e.path, region.landmark, length(chain) AS distance
                ORDER BY p.url, e.path, distance
                """
            )
            regions: Dict[str, Dict[str, str]] = {}
            for page_url, path, landmark, _distance in rows:
                by_path = regions.setdefault(page_url, {})
                if path not in by_path:
                    by_path[path] = landmark
            return regions

        return self._call(op)

    def get_page_landmarks(self) -> Dict[str, Dict[str, int]]:
        """How many distinct landmark regions of each kind a page has -
        `{page_url: {landmark: count}}`.

        The question `generators/accessibility.py` asks that
        `get_component_regions` cannot answer: that one reports the region a
        *component* sits in, so a page with two separate `<header>`s looks
        identical to a page with one. Landmark structure is a property of the
        page, not of any component in it.

        `count(DISTINCT region.id)` rather than `count(region.id)` - confirmed
        against the real engine that the difference is real here: two banners
        holding three components between them count 3 naively and 2 distinctly,
        and 2 is the answer WCAG cares about.

        Reached through components, not `HAS_CONTAINER` directly: a landmark
        holding no discovered component is invisible here regardless, since
        this still asks "how many regions does a component sit inside", not
        "how many `Container` rows exist on this page" - an empty region has
        nothing to be inaccessible about.

        Returns:
            One entry per page with at least one landmark region. `{}` for a
            site whose crawl recorded no ancestry at all.
        Details: docs/dev/database/ladybug/containment.md#get_page_landmarks
        """
        def op(conn) -> Dict[str, Dict[str, int]]:
            rows = conn.execute(
                """
                MATCH (p:Page)-[:HAS_COMPONENT]->(comp:Component)
                MATCH (region:Container)-[:CONTAINS*1..8]->(comp)
                WHERE region.landmark <> ''
                RETURN p.url, region.landmark, count(DISTINCT region.id)
                ORDER BY p.url, region.landmark
                """
            )
            landmarks: Dict[str, Dict[str, int]] = {}
            for page_url, landmark, count in rows:
                landmarks.setdefault(page_url, {})[landmark] = count
            return landmarks

        return self._call(op)
