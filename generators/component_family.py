"""Pure, deterministic inference of reusable component "families" (a button
pattern, a dropdown pattern, ...) from already-discovered components - no
I/O, no LLM, same placement discipline as component_classifier.py.

What this solves: a crawl discovers every interactive element as its own
independent `Component` node (e.g. 8 separate "Agregar" buttons across a
site). A human looking at the graph wants to know they're really 8 uses
of *one* reusable button pattern, not 8 unrelated facts. This module infers
that grouping after the fact from what a crawl already captured (each
component's `tag`, `component_type`, `css_class`) - it never talks to a
browser or a graph database itself; `analysis/component_clustering.py::
apply_component_families` is the only caller, and it does all the I/O
(reading `GraphStore.get_component_ledger`, writing the results back via
`GraphStore.record_component_families`).

`build_component_families` groups components that aren't just the same
*kind* of tag, but structurally the same reusable *pattern* (same
`component_type` and a similar-enough `css_class`) - answering "which of
these components are really the same button, just used in different
places (or with a different color/state)". A coarser, purely tag-based
grouping (`tags_with_multiple_instances`/`label_for_tag`) used to live
here too, feeding `GraphStore.apply_tag_labels` so Neo4j Browser could
color nodes by tag - removed along with that backend, since it was purely
a Browser-coloring affordance with no equivalent once nothing renders the
graph visually.

Details: docs/dev/generators/component_family.md#module
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Set, Tuple

from core.interfaces import ComponentFamily

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
    """Split one component's `css_class` string into a comparable token set.

    Args:
        css_class: raw space-separated class attribute value, e.g.
            `"btn btn-primary rounded"`. `""` or `None` both mean "no
            classes at all", not an error.

    Returns:
        A `frozenset` of the individual class names, e.g.
        `frozenset({"btn", "btn-primary", "rounded"})`. Empty
        (`frozenset()`) for an element with no classes.
    """
    return frozenset((css_class or "").split())


def _similarity(a: FrozenSet[str], b: FrozenSet[str]) -> float:
    """Jaccard similarity between two components' class-token sets - the
    fraction of the combined class vocabulary they actually share.

    Args:
        a: one component's tokens, from `_class_tokens`.
        b: another component's tokens, from `_class_tokens`.

    Returns:
        A float in `[0.0, 1.0]`. `len(a & b) / len(a | b)` in the normal
        case (e.g. `{"btn", "btn-primary"}` vs. `{"btn", "btn-secondary"}`
        -> `1/3 ≈ 0.33`). Two special cases override that formula (which
        would otherwise divide by zero or be misleading):
        - `1.0` when both `a` and `b` are empty - two elements with no
          classes at all read as visually identical, not "no overlap".
        - `0.0` when exactly one of `a`/`b` is empty - an unstyled and a
          styled element are never the same family, no matter how few
          classes the styled one has.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    """Minimal union-find (disjoint-set) structure for clustering
    same-bucket components whose class sets are pairwise similar enough.

    Single-linkage: `union(i, j)` only asserts "i and j belong together",
    the same *set* i and j end up in can still contain members that
    aren't directly similar to each other, chained through intermediate
    members that are. Accepted for this feature's purpose (a helpful
    grouping for a migration PRD, not a database-critical dedup); revisit
    only if that chaining shows up as a real problem on a real site, not
    preemptively.
    """

    def __init__(self, size: int) -> None:
        """Args:
            size: number of elements to track, indexed `0..size-1`. Every
                element starts in its own singleton set.
        """
        self._parent = list(range(size))

    def find(self, i: int) -> int:
        """The representative index of the set `i` currently belongs to.

        Args:
            i: element index, `0..size-1` from `__init__`.

        Returns:
            An index that's the same for every element in `i`'s set (not
            necessarily `i` itself) - two elements are in the same set
            exactly when `find(i) == find(j)`.
        """
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        """Merge `i`'s set and `j`'s set into one. No return value; query
        the result afterward via `find`.

        Args:
            i: element index.
            j: element index.
        """
        root_i, root_j = self.find(i), self.find(j)
        if root_i != root_j:
            self._parent[root_i] = root_j


def _cluster_bucket(members: List[Dict]) -> List[List[int]]:
    """Group one `(tag, component_type)` bucket's members by pairwise
    class-set similarity (`_similarity` >= `_SIMILARITY_THRESHOLD`).

    Args:
        members: components already known to share the same `tag` and
            `component_type` (a `build_component_families` bucket) - each
            a dict that needs at least a `"css_class"` key.

    Returns:
        A list of clusters, each cluster a list of indices into `members`
        (not the member dicts themselves). Every index in `0..len(members)`
        appears in exactly one cluster - a member with no similar sibling
        is its own single-element cluster, filtered out by the caller
        (`build_component_families`) rather than here, since "is this
        cluster big enough to be a family" is that caller's own concern,
        not this clustering step's.
    """
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
    """Group `components` into inferred reusable-component families.

    Bucketed first by `(tag, component_type)` so nothing ever merges
    across element kinds regardless of class overlap - a button and an
    input sharing layout utility classes never compete for the same
    family. Within a bucket, members whose `css_class` tokens are
    Jaccard-similar enough (see `_similarity_threshold`'s own comment for
    why plain, unweighted similarity is the deliberate choice here) get
    clustered together; a cluster becomes a `ComponentFamily` only once
    it has `_MIN_FAMILY_SIZE` (2) or more members - a component with no
    matching sibling anywhere on the site isn't returned as a family at
    all, it's simply absent from the output.

    Args:
        components: every component discovered for one site, flattened
            to one dict per component (not the page-nested shape
            `GraphStore.get_component_ledger` returns - see
            `Engine._apply_component_families` for the flattening step).
            Each dict needs:
            - `"page_url"` (str): which page this instance lives on.
            - `"path"` (str): this instance's own CSS selector path -
              together with `page_url`, uniquely identifies one
              `Component` node.
            - `"tag"` (str): raw HTML tag, e.g. `"button"`, `"input"`,
              `"a"`. Components with a falsy/missing tag are silently
              skipped (never a KeyError) - a defensive floor, not
              expected to trigger in the normal crawl-driven path.
            - `"component_type"` (str): the human-readable role label
              `component_classifier.classify_component_type` already
              computed at crawl time, e.g. `"button"`, `"submit
              button"`, `"checkbox"`, `"combobox (searchable
              dropdown)"`, `"text field (text)"`, `"link"`. Two
              components with the same `tag` but a different
              `component_type` (e.g. a plain `<button>` vs. a `<button
              type="submit">`) never share a family, even with
              identical classes.
            - `"css_class"` (str): the element's raw class attribute
              value, e.g. `"btn btn-primary"`. `""`/missing means "no
              classes".

    Returns:
        One `ComponentFamily` (see `core/interfaces.py`) per cluster
        that reached `_MIN_FAMILY_SIZE`:
        - `tag`/`component_type`: the bucket's own key, shared by every
          member.
        - `common_classes`: a sorted tuple of the classes *every* member
          has in common - the family's visual "signature" (e.g.
          `("btn", "rounded")` for a primary/secondary pair that only
          differs by its color-modifier class).
        - `member_paths`: a sorted tuple of `(page_url, path)` pairs, one
          per member - sorted so the result is deterministic regardless
          of input order or clustering iteration order, and so it
          compares equal to what `DuckDBGraphStore.get_component_families`
          reads back (that method has its own matching `ORDER BY`).
        No family is returned for a bucket where every member is a
        singleton (no two members meet the similarity threshold) - the
        return list can be shorter than the number of distinct
        `(tag, component_type)` buckets, or empty entirely.

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
                    # regardless of clustering/iteration order - a
                    # round-trip through any backend compares equal.
                    member_paths=tuple(sorted((m["page_url"], m["path"]) for m in cluster)),
                )
            )
    return families
