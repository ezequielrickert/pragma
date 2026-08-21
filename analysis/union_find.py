"""Minimal union-find (disjoint-set) - shared by every clustering step in
`component_matching_pipeline.py` (leaf exact/family, composite exact/
family) that needs to turn a set of pairwise "these two belong together"
verdicts into groups. Single-linkage: `union(i, j)` only asserts "i and j
belong together" - the set i and j end up in can still contain members
that aren't directly similar to each other, chained through intermediate
members that are. The same tradeoff `generators/component_family.py`'s
retired Jaccard clustering made for the same reason: a helpful grouping,
not a guarantee every pair within it clears the threshold directly.

Details: docs/dev/analysis/union_find.md#module
"""
from __future__ import annotations


class UnionFind:
    """Details: docs/dev/analysis/union_find.md#unionfind"""

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

    def groups(self) -> "list[list[int]]":
        """Every current set, as a list of member indices - `find`'s
        result grouped back into the sets it partitions `0..size-1` into.
        Details: docs/dev/analysis/union_find.md#groups
        """
        clusters: "dict[int, list[int]]" = {}
        for i in range(len(self._parent)):
            clusters.setdefault(self.find(i), []).append(i)
        return list(clusters.values())
