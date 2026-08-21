"""The component-matching pipeline - issue #135's design, run against a
real graph store for the first time (issue #139): leaf exact collapse,
leaf family grouping, composite exact collapse, composite family
grouping, in that order. Replaces `analysis/component_clustering.py::
apply_component_families` outright, per the map's founding decision that
`generators/component_family.py`'s Jaccard clustering gets replaced, not
extended - there is no case where both should run.

`apply_component_matching` is the one entry point, called from
`core/cluster_engine.py` (`pragma cluster`) and `core/engine.py` (the
fused crawl+analyze run) - the same two call sites `apply_component_
families` used to have.

Details: docs/dev/analysis/component_matching_pipeline.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import Agent, ComponentFamily, CompositeFamily
from generators.component_family_narrator import family_signature, narrate_family_purposes
from generators.ledger import flat_component_ledger
from .component_matching_config import ComponentMatchingConfig
from .composite_matching import ContainerNode, bucket_candidates, classify_composite_match, composite_score
from .leaf_feature_vector import GeometryBuckets, compute_geometry_buckets, leaf_feature_vector
from .union_find import UnionFind
from .vector_similarity import cosine_similarity

MergeGroups = List[Tuple[str, List[str]]]


def apply_component_matching(graph_store: Any, agent: Agent, config: Optional[ComponentMatchingConfig] = None) -> None:
    """Run the whole four-step pipeline once, over whatever the graph
    store currently holds - the direct replacement for `analysis/
    component_clustering.py::apply_component_families`, same call
    contract (reads and writes through `graph_store`, narrates leaf
    families via `agent`).
    Details: docs/dev/analysis/component_matching_pipeline.md#apply_component_matching
    """
    config = config or ComponentMatchingConfig.load()

    components = flat_component_ledger(graph_store)
    geometry_buckets = compute_geometry_buckets(components)
    exact_leaf_groups = _leaf_merge_groups(components, geometry_buckets, config, config.thresholds.leaf_exact)
    if exact_leaf_groups:
        graph_store.merge_components(exact_leaf_groups)
        merged = sum(len(absorbed) for _, absorbed in exact_leaf_groups)
        print(f"Leaf exact collapse: merged {merged} components into {len(exact_leaf_groups)} canonical rows.")

    components = flat_component_ledger(graph_store)  # re-read: exact collapse changed the component set
    geometry_buckets = compute_geometry_buckets(components)
    families = _build_leaf_families(components, geometry_buckets, config)
    print(f"Grouped {len(components)} components into {len(families)} families.")
    _narrate_and_record_leaf_families(graph_store, agent, components, families)

    forest = graph_store.get_container_forest()
    unique_roots, root_paths = _dedup_composite_roots(forest)
    exact_composite_groups = _composite_merge_groups(unique_roots, geometry_buckets, config, "exact")
    if exact_composite_groups:
        graph_store.merge_containers(exact_composite_groups)
        merged = sum(len(absorbed) for _, absorbed in exact_composite_groups)
        print(f"Composite exact collapse: merged {merged} composites into {len(exact_composite_groups)} canonical roots.")

    forest = graph_store.get_container_forest()  # re-read: exact collapse changed the composite set
    unique_roots, root_paths = _dedup_composite_roots(forest)
    composite_families = _build_composite_families(unique_roots, root_paths, geometry_buckets, config)
    print(f"Grouped {len(unique_roots)} composites into {len(composite_families)} composite families.")
    graph_store.record_composite_families(composite_families)


def _member_key(component: Dict[str, Any]) -> str:
    return f"{component['page_url']}|{component['path']}"


def _leaf_merge_groups(
    components: List[Dict[str, Any]],
    geometry_buckets: GeometryBuckets,
    config: ComponentMatchingConfig,
    threshold: float,
) -> MergeGroups:
    """`(canonical_id, [absorbed_id, ...])` per exact-tier cluster -
    bucketed by `(tag, component_type)` (same discipline the retired
    Jaccard clustering used), then union-find over pairwise leaf-vector
    cosine similarity `>= threshold` within each bucket. The canonical
    row is whichever cluster member sorts first by `(page_url, path)` -
    deterministic and arbitrary, defensible only because every member's
    content is already near-identical by construction at this threshold.
    A cluster can name the same `Component` id more than once (two
    ledger entries - two pages rendering an already-canonical component -
    landing in the same cluster); `merge_components` already de-duplicates
    a group's own absorbed ids against its canonical one, so a same-id
    "self merge" inside one cluster is a safe no-op, not a bug.
    Details: docs/dev/analysis/component_matching_pipeline.md#_leaf_merge_groups
    """
    buckets: Dict[Tuple[str, str], List[int]] = {}
    for i, component in enumerate(components):
        buckets.setdefault((component.get("tag", ""), component.get("component_type", "")), []).append(i)

    groups: MergeGroups = []
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        vectors = [leaf_feature_vector(components[i], geometry_buckets, config) for i in indices]
        union_find = UnionFind(len(indices))
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                if cosine_similarity(vectors[a], vectors[b]) >= threshold:
                    union_find.union(a, b)
        for cluster in union_find.groups():
            members = sorted((indices[m] for m in cluster), key=lambda i: _member_key(components[i]))
            canonical_id = components[members[0]]["id"]
            absorbed_ids = sorted({components[i]["id"] for i in members[1:]} - {canonical_id})
            if absorbed_ids:
                groups.append((canonical_id, absorbed_ids))
    return groups


def _build_leaf_families(
    components: List[Dict[str, Any]], geometry_buckets: GeometryBuckets, config: ComponentMatchingConfig,
) -> List[ComponentFamily]:
    """`ComponentFamily` per family-tier cluster - same bucketing/union-
    find shape as `_leaf_merge_groups`, at `thresholds.leaf_family`
    instead. Run *after* exact collapse (the caller's own responsibility
    to sequence), so every cluster here is a genuine "similar, not
    identical" grouping - anything closer already became one row.
    Details: docs/dev/analysis/component_matching_pipeline.md#_build_leaf_families
    """
    buckets: Dict[Tuple[str, str], List[int]] = {}
    for i, component in enumerate(components):
        buckets.setdefault((component.get("tag", ""), component.get("component_type", "")), []).append(i)

    families: List[ComponentFamily] = []
    for (tag, component_type), indices in buckets.items():
        if len(indices) < 2:
            continue
        vectors = [leaf_feature_vector(components[i], geometry_buckets, config) for i in indices]
        union_find = UnionFind(len(indices))
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                if cosine_similarity(vectors[a], vectors[b]) >= config.thresholds.leaf_family:
                    union_find.union(a, b)
        for cluster in union_find.groups():
            members = [components[indices[m]] for m in cluster]
            # A "family" means several *distinct* canonical components
            # grouped as similar variants - a cluster whose every ledger
            # entry already resolves to the same id is just one already-
            # canonical component's multi-page presence, not a family of
            # anything. Ledger-entry count alone can't tell those apart
            # (an exact-collapsed component legitimately produces one
            # entry per page it's rendered on), so the id set is what's
            # actually checked.
            if len({m["id"] for m in members}) < 2:
                continue
            member_paths = tuple(sorted({(m["page_url"], m["path"]) for m in members}))
            common_classes = _common_classes(members)
            families.append(ComponentFamily(
                tag=tag, component_type=component_type, common_classes=common_classes,
                member_paths=member_paths, purpose="",
            ))
    return families


def _common_classes(members: List[Dict[str, Any]]) -> Tuple[str, ...]:
    token_sets = [frozenset((m.get("css_class") or "").split()) for m in members]
    shared = token_sets[0]
    for tokens in token_sets[1:]:
        shared = shared & tokens
    return tuple(sorted(shared))


def _narrate_and_record_leaf_families(
    graph_store: Any, agent: Agent, components: List[Dict[str, Any]], families: List[ComponentFamily],
) -> None:
    member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
    # Read before record_component_families wipes them - a family whose
    # members did not change keeps its sentence rather than buying it
    # again, same reasoning apply_component_families followed.
    known_purposes = {
        family_signature(existing): existing.purpose
        for existing in graph_store.get_component_families()
        if existing.purpose
    }
    narrated = narrate_family_purposes(agent, families, member_texts, known_purposes)
    graph_store.record_component_families(narrated)


def _dedup_composite_roots(
    forest: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, ContainerNode], Dict[str, List[Tuple[str, str]]]]:
    """`{id: ContainerNode}` deduplicated across every page, plus
    `{id: [(page_url, path), ...]}` - a canonical `Container` root shared
    by several pages appears once per page in `forest` (the same node,
    not a copy worth re-comparing against itself), so matching runs
    against the deduplicated set while family membership still needs
    every page it actually renders on.
    Details: docs/dev/analysis/component_matching_pipeline.md#_dedup_composite_roots
    """
    roots: Dict[str, ContainerNode] = {}
    root_paths: Dict[str, List[Tuple[str, str]]] = {}
    for page_url, page_roots in forest.items():
        for root in page_roots:
            root_paths.setdefault(root["id"], []).append((page_url, root["path"]))
            if root["id"] not in roots:
                roots[root["id"]] = _to_container_node(root)
    return roots, root_paths


def _to_container_node(node: Dict[str, Any]) -> ContainerNode:
    children = [
        _to_container_node(child) if "children" in child else child
        for child in node.get("children", [])
    ]
    return ContainerNode(
        id=node["id"], tag=node.get("tag", ""), role=node.get("role", ""),
        landmark=node.get("landmark", ""), css_class=node.get("css_class", ""), children=children,
    )


def _composite_merge_groups(
    roots: Dict[str, ContainerNode], geometry_buckets: GeometryBuckets, config: ComponentMatchingConfig, tier: str,
) -> MergeGroups:
    """`(canonical_id, [absorbed_id, ...])` per exact-tier composite
    cluster - candidate pairs from `bucket_candidates`, scored via
    `composite_score`, unioned only when `classify_composite_match`
    reaches `tier` (`"exact"`, the only tier this pipeline merges rows
    for - family membership never collapses anything).
    Details: docs/dev/analysis/component_matching_pipeline.md#_composite_merge_groups
    """
    id_list = list(roots.keys())
    index_of = {container_id: i for i, container_id in enumerate(id_list)}
    union_find = UnionFind(len(id_list))
    cache: Dict[Tuple[str, str], Any] = {}
    for container_a, container_b in bucket_candidates(list(roots.values()), config.composite_bucketing.child_count_slack):
        result = composite_score(container_a, container_b, geometry_buckets, config, cache)
        if classify_composite_match(result, config) == tier:
            union_find.union(index_of[container_a.id], index_of[container_b.id])

    groups: MergeGroups = []
    for cluster in union_find.groups():
        if len(cluster) < 2:
            continue
        member_ids = sorted(id_list[i] for i in cluster)
        canonical_id, absorbed_ids = member_ids[0], member_ids[1:]
        groups.append((canonical_id, absorbed_ids))
    return groups


def _build_composite_families(
    roots: Dict[str, ContainerNode],
    root_paths: Dict[str, List[Tuple[str, str]]],
    geometry_buckets: GeometryBuckets,
    config: ComponentMatchingConfig,
) -> List[CompositeFamily]:
    """`CompositeFamily` per family-tier composite cluster - same shape
    as `_composite_merge_groups`, but every cluster with 2+ members
    becomes a family instead of a merge, coverage gap or not, per #132's
    family-tier rule.
    Details: docs/dev/analysis/component_matching_pipeline.md#_build_composite_families
    """
    id_list = list(roots.keys())
    index_of = {container_id: i for i, container_id in enumerate(id_list)}
    union_find = UnionFind(len(id_list))
    cache: Dict[Tuple[str, str], Any] = {}
    for container_a, container_b in bucket_candidates(list(roots.values()), config.composite_bucketing.child_count_slack):
        result = composite_score(container_a, container_b, geometry_buckets, config, cache)
        if classify_composite_match(result, config) != "none":
            union_find.union(index_of[container_a.id], index_of[container_b.id])

    families: List[CompositeFamily] = []
    for cluster in union_find.groups():
        if len(cluster) < 2:
            continue
        member_ids = [id_list[i] for i in cluster]
        member_paths = tuple(sorted({pair for cid in member_ids for pair in root_paths.get(cid, [])}))
        root_tag = roots[member_ids[0]].tag
        families.append(CompositeFamily(root_tag=root_tag, member_paths=member_paths, purpose=""))
    return families
