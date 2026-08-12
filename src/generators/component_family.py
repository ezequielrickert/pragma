"""Pure, deterministic inference of reusable component "families" (a button
pattern, a dropdown pattern, ...) from already-discovered components - no
I/O, no LLM, same placement discipline as component_classifier.py.
Details: docs/dev/generators/component_family.md#module
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, FrozenSet, List, Set, Tuple

from ..core.interfaces import ComponentFamily

# Jaccard similarity floor, over css_class tokens, for two same-(tag,
# component_type) components to count as variants of one reusable family.
# Scoped strictly within a (tag, component_type) bucket first (see
# build_component_families) - two classes shared by every member of the
# bucket (a layout/sizing utility class, say) contribute the same weight
# as a state-specific one (a color modifier), so plain overlap is what
# actually matches the intent here: a "primary" and a "secondary" button
# sharing every class but the color modifier read as clearly the same
# family (high overlap), while genuinely different widgets that happen to
# share a few layout utility classes don't reach this threshold as long as
# they differ in most of their remaining classes.
# Details: docs/dev/generators/component_family.md#_similarity_threshold
_SIMILARITY_THRESHOLD = 0.5

# A family needs at least this many members to be worth its own node - one
# component with no siblings isn't a reusable pattern, it's just a
# component. Also the bar for "this tag is common enough to deserve its
# own label" (see tags_with_multiple_instances) - same "at least one
# sibling" reasoning in both places.
# Details: docs/dev/generators/component_family.md#_min_family_size
_MIN_FAMILY_SIZE = 2


def _class_tokens(css_class: str) -> FrozenSet[str]:
    return frozenset((css_class or "").split())


def _similarity(a: FrozenSet[str], b: FrozenSet[str]) -> float:
    """1.0 when both sets are empty (two unstyled elements read as
    identical), 0.0 when only one is - an unstyled and a styled element
    are never the same family, regardless of how few tokens the styled
    side has.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    """Minimal union-find for clustering same-bucket components whose
    class sets are pairwise similar enough - single-linkage, so a chain of
    pairwise-similar members can end up in one cluster even if the two
    most distant members in it aren't directly similar. Accepted for this
    feature's purpose (a helpful grouping, not a database-critical dedup);
    revisit only if that chaining shows up as a real problem on a real
    site, not preemptively.
    """

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, i: int) -> int:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        root_i, root_j = self.find(i), self.find(j)
        if root_i != root_j:
            self._parent[root_i] = root_j


def _cluster_bucket(members: List[Dict]) -> List[List[int]]:
    """Indices of `members` grouped by pairwise class-set similarity."""
    token_sets = [_class_tokens(m.get("css_class", "")) for m in members]
    uf = _UnionFind(len(members))
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if _similarity(token_sets[i], token_sets[j]) >= _SIMILARITY_THRESHOLD:
                uf.union(i, j)

    clusters: Dict[int, List[int]] = {}
    for idx in range(len(members)):
        clusters.setdefault(uf.find(idx), []).append(idx)
    return list(clusters.values())


def build_component_families(components: List[Dict]) -> List[ComponentFamily]:
    """Group `components` (each needs "page_url", "path", "tag",
    "component_type", "css_class") into families.
    Bucketed first by (tag, component_type) so nothing ever merges across
    element kinds regardless of class overlap - a button and an input
    sharing layout utility classes never compete for the same family.
    Details: docs/dev/generators/component_family.md#build_component_families
    """
    buckets: Dict[Tuple[str, str], List[Dict]] = {}
    for comp in components:
        tag = comp.get("tag") or ""
        if not tag:
            continue
        buckets.setdefault((tag, comp.get("component_type") or ""), []).append(comp)

    families: List[ComponentFamily] = []
    for (tag, component_type), members in buckets.items():
        if len(members) < _MIN_FAMILY_SIZE:
            continue
        for indices in _cluster_bucket(members):
            if len(indices) < _MIN_FAMILY_SIZE:
                continue
            cluster = [members[i] for i in indices]
            common = set.intersection(*(set(_class_tokens(m.get("css_class", ""))) for m in cluster))
            families.append(
                ComponentFamily(
                    tag=tag,
                    component_type=component_type,
                    common_classes=tuple(sorted(common)),
                    # Sorted so a family's member order is deterministic
                    # regardless of clustering/iteration order - matches
                    # Neo4jGraphStore.get_component_families's own explicit
                    # ORDER BY, so a round-trip through either backend
                    # compares equal.
                    member_paths=tuple(sorted((m["page_url"], m["path"]) for m in cluster)),
                )
            )
    return families


# `<a>` reads as "Link" - the bare letter "A" is not a usable node label
# in practice. Everything else just capitalizes its own tag name.
# Details: docs/dev/generators/component_family.md#_tag_label_overrides
_TAG_LABEL_OVERRIDES = {"a": "Link"}


def label_for_tag(tag: str) -> str:
    """Human-readable, Cypher-label-safe name for a raw HTML tag.
    `"Component"` for anything that isn't a plain identifier (a custom
    element like `<my-widget>`, whose hyphen isn't valid in an
    unescaped Cypher label) - falls back to the generic label rather than
    risk building an invalid label into a query string.
    Details: docs/dev/generators/component_family.md#label_for_tag
    """
    tag = (tag or "").lower()
    if tag in _TAG_LABEL_OVERRIDES:
        return _TAG_LABEL_OVERRIDES[tag]
    return tag.capitalize() if tag.isidentifier() else "Component"


def tags_with_multiple_instances(components: List[Dict]) -> Set[str]:
    """Tags worth their own label - appearing on `_MIN_FAMILY_SIZE`+
    components for this site. A tag seen only once has no "type" to
    speak of yet, so it stays generic.
    Details: docs/dev/generators/component_family.md#tags_with_multiple_instances
    """
    counts = Counter(c.get("tag") or "" for c in components)
    return {tag for tag, count in counts.items() if tag and count >= _MIN_FAMILY_SIZE}
