"""Whole-site composite-tree read for `LadybugGraphStore` - what
`analysis/composite_matching.py`'s matching pass (issue #139) needs before
it can bucket or score anything. `_LadybugContainerForestMixin` is
combined into the public `LadybugGraphStore` class via multiple
inheritance and relies on `self._call(...)` existing on whatever it ends
up mixed into.

Its own module rather than part of `containment.py` (already at this
project's file-size watch threshold): a different concern from that file's
write path - this reads the whole site's composite structure back, once,
for the matching pass, not one page's `CONTAINS` chain as the crawl
discovers it.

Details: docs/dev/database/ladybug/container_forest.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .schema import DESCRIPTIVE_COMPONENT_FIELDS


class _LadybugContainerForestMixin:
    """Details: docs/dev/database/ladybug/container_forest.md#_ladybugcontainerforestmixin"""

    def get_container_forest(self) -> Dict[str, List[Dict[str, Any]]]:
        """`{page_url: [root_dict, ...]}` - every page's top-level
        composites, each a nested tree whose `children` mix leaf component
        dicts (same shape `analysis/leaf_feature_vector.py::
        leaf_feature_vector` takes) and nested composite dicts recursively
        shaped the same way as the root.

        A composite is a page's *root* if no other composite on that same
        page `CONTAINS` it - a `Container` shared across pages can
        legitimately be a root on one page and a nested child on another,
        so root-ness is judged per page, not globally.

        Read as four whole-site queries, not one root at a time recursed
        via `CONTAINS*` - a real site's composite count is small enough to
        hold entirely in memory (unlike the components underneath them),
        and building the tree in Python avoids one round trip per
        nesting level per root.
        Details: docs/dev/database/ladybug/container_forest.md#get_container_forest
        """
        fields = ", ".join(f"c.{field}" for field in DESCRIPTIVE_COMPONENT_FIELDS)

        def op(conn) -> Dict[str, List[Dict[str, Any]]]:
            containers = {
                row[0]: {"id": row[0], "tag": row[1], "role": row[2], "landmark": row[3], "css_class": row[4]}
                for row in conn.execute("MATCH (n:Container) RETURN n.id, n.tag, n.role, n.landmark, n.css_class")
            }
            components = {
                row[0]: dict(zip(DESCRIPTIVE_COMPONENT_FIELDS, row[1:]))
                for row in conn.execute(f"MATCH (c:Component) RETURN c.id, {fields}")
            }
            nested_containers: Dict[str, List[str]] = {}
            for parent_id, child_id in conn.execute("MATCH (p:Container)-[:CONTAINS]->(c:Container) RETURN p.id, c.id"):
                nested_containers.setdefault(parent_id, []).append(child_id)
            nested_components: Dict[str, List[str]] = {}
            for parent_id, child_id in conn.execute("MATCH (p:Container)-[:CONTAINS]->(c:Component) RETURN p.id, c.id"):
                nested_components.setdefault(parent_id, []).append(child_id)
            page_containers: Dict[str, List[str]] = {}
            root_path: Dict[Tuple[str, str], str] = {}
            for page_url, path, container_id in conn.execute(
                "MATCH (p:Page)-[e:HAS_CONTAINER]->(n:Container) RETURN p.url, e.path, n.id"
            ):
                page_containers.setdefault(page_url, []).append(container_id)
                root_path[(page_url, container_id)] = path

            forest: Dict[str, List[Dict[str, Any]]] = {}
            for page_url, container_ids in page_containers.items():
                on_page = set(container_ids)
                nested_on_page = {
                    child for cid in container_ids for child in nested_containers.get(cid, []) if child in on_page
                }
                roots = [cid for cid in container_ids if cid not in nested_on_page]
                page_roots = []
                for root_id in roots:
                    tree = _build_composite_tree(root_id, containers, nested_containers, nested_components, components, frozenset())
                    # Only the root itself carries `path` - the literal
                    # selector a *page* renders it at, which only makes
                    # sense for the top of the tree the pipeline bucketed
                    # by; a nested child's own path isn't needed for
                    # matching and would vary per ancestor anyway.
                    tree["path"] = root_path[(page_url, root_id)]
                    page_roots.append(tree)
                forest[page_url] = page_roots
            return forest

        return self._call(op)


def _build_composite_tree(
    container_id: str,
    containers: Dict[str, Dict[str, Any]],
    nested_containers: Dict[str, List[str]],
    nested_components: Dict[str, List[str]],
    components: Dict[str, Dict[str, Any]],
    ancestors: frozenset,
) -> Dict[str, Any]:
    """One composite's tree, recursively. `ancestors` guards against a
    cycle a genuine DOM tree can never produce but a canonical, shared
    `Container` reused in an unexpected shape could in principle - a
    child already on the current path is dropped rather than recursed
    into again.
    Details: docs/dev/database/ladybug/container_forest.md#_build_composite_tree
    """
    node = dict(containers[container_id])
    children: List[Dict[str, Any]] = []
    for child_id in nested_containers.get(container_id, []):
        if child_id in ancestors or child_id not in containers:
            continue
        children.append(
            _build_composite_tree(child_id, containers, nested_containers, nested_components, components,
                                   ancestors | {container_id})
        )
    for component_id in nested_components.get(container_id, []):
        if component_id in components:
            children.append(dict(components[component_id]))
    node["children"] = children
    return node
