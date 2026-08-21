"""Composite/subtree matching - issue #132's design
(`docs/dev/generators/composite-subtree-matching-design.md`), implemented
here as pure functions over an in-memory `Container`/`Component` tree. No
I/O, no graph store - reading a live `CONTAINS` traversal into
`ContainerNode`s and wiring the result into the pipeline is issue #139's
job, not this module's.

`ContainerNode` is a plain, hand-buildable tree (same convention as
`leaf_feature_vector.py`'s flat component dicts): a `Container` root's own
identity fields plus its `children`, each either a leaf component dict
(same shape `leaf_feature_vector` takes) or a nested `ContainerNode`.

`composite_score` is the module's one real entry point - a coverage-
weighted similarity between two composites, with the bipartite child-to-
child correspondence (`CompositeMatchResult.matched_pairs`) as a byproduct,
not a separate computation: whichever nav link on page A paired with
whichever nav link on page B is exactly "which button leads where" staying
individually addressable after the parent collapses.

Details: docs/dev/analysis/composite_matching.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .component_matching_config import ComponentMatchingConfig
from .hungarian import min_cost_assignment
from .leaf_feature_vector import GeometryBuckets, _hash_multi_hot, _hash_one_hot, leaf_feature_vector
from .vector_similarity import cosine_similarity

_ROOT_TAG_BUCKETS = 16
_ROOT_ROLE_BUCKETS = 16
_ROOT_LANDMARK_BUCKETS = 16
_ROOT_CSS_CLASS_BUCKETS = 32


@dataclass
class ContainerNode:
    """One `Container` root or subtree. `children` mixes leaf component
    dicts and nested `ContainerNode`s, matching what a `CONTAINS`
    traversal actually returns - a composite's direct children are
    whichever mix of `Component`/`Container` rows it directly contains.
    `id` only needs to be unique within one matching run - it is the
    memoization key `composite_score` caches nested-composite results
    under, not a real `Container.id`.
    Details: docs/dev/analysis/composite_matching.md#containernode
    """

    id: str
    tag: str = ""
    role: str = ""
    landmark: str = ""
    css_class: str = ""
    children: Sequence[Union["ContainerNode", Dict[str, Any]]] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompositeMatchResult:
    """One pairwise composite comparison's full outcome - `score` is the
    scalar a threshold compares against; `matched_pairs`/`root_similarity`
    are what a caller needing the *why* (which child paired with which)
    or a coverage check reads instead of recomputing them.
    Details: docs/dev/analysis/composite_matching.md#compositematchresult
    """

    root_similarity: float
    matched_pairs: Tuple[Tuple[int, int], ...]
    score: float
    full_coverage: bool


def container_root_vector(container: ContainerNode, config: Optional[ComponentMatchingConfig] = None) -> List[float]:
    """A `Container` root's own vector - `tag`/`role`/`landmark` hashed
    into the structural block the same way a leaf's `tag`/`role` are
    (#131's encoding), plus `css_class` as its own weighted slice.
    `element_id` is excluded, same precedent as leaf `Component`s; a
    `Container` carries no style/geometry to encode (`schema.py`'s DDL
    gives it none), so this vector is smaller than a leaf's, not a
    truncated copy of it.
    Details: docs/dev/analysis/composite_matching.md#container_root_vector
    """
    weights = (config or ComponentMatchingConfig()).leaf_weights
    structural = (
        _hash_one_hot(container.tag, _ROOT_TAG_BUCKETS)
        + _hash_one_hot(container.role, _ROOT_ROLE_BUCKETS)
        + _hash_one_hot(container.landmark, _ROOT_LANDMARK_BUCKETS)
    )
    css_class = _hash_multi_hot((container.css_class or "").split(), _ROOT_CSS_CLASS_BUCKETS)
    return [v * weights.structural for v in structural] + [v * weights.css_class for v in css_class]


def bucket_candidates(
    containers: Sequence[ContainerNode], child_count_slack: float
) -> List[Tuple[ContainerNode, ContainerNode]]:
    """Candidate pairs cheap enough to score - grouped by `(tag, role)`
    first (a `Container`'s closest analog to a leaf's `(tag,
    component_type)` bucket key; `Container` carries no `component_type`
    of its own), then any pair whose child counts differ by more than
    `child_count_slack` of the larger side is dropped before any per-child
    work runs - same discipline `component_family.py` already applies
    before its own comparison pass.
    Details: docs/dev/analysis/composite_matching.md#bucket_candidates
    """
    buckets: Dict[Tuple[str, str], List[ContainerNode]] = {}
    for container in containers:
        buckets.setdefault((container.tag, container.role), []).append(container)

    pairs: List[Tuple[ContainerNode, ContainerNode]] = []
    for members in buckets.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                first, second = members[i], members[j]
                larger = max(len(first.children), len(second.children))
                if larger == 0:
                    pairs.append((first, second))
                    continue
                if abs(len(first.children) - len(second.children)) <= child_count_slack * larger:
                    pairs.append((first, second))
    return pairs


def composite_score(
    container_a: ContainerNode,
    container_b: ContainerNode,
    geometry_buckets: GeometryBuckets,
    config: Optional[ComponentMatchingConfig] = None,
    _cache: Optional[Dict[Tuple[str, str], CompositeMatchResult]] = None,
) -> CompositeMatchResult:
    """One pair's coverage-weighted composite score:

        (root_similarity + sum(matched_pair_similarities)) / (1 + max(children_a, children_b))

    Root similarity is one term among the children's, not a separate
    gate. Children are matched via optimal bipartite assignment
    (`hungarian.py`) over every cross-pair's similarity - a leaf compared
    against a leaf uses `leaf_feature_vector`'s cosine similarity directly;
    a `Container` child compared against a `Container` child recurses into
    this same function, memoized in `_cache` by `(id, id)` so a nested
    composite that shows up as a child in several candidate pairings is
    scored once, not once per ancestor pair that happens to reach it. A
    leaf can never match a composite root, so that cross-kind pair scores
    `0.0`. Unmatched children (a count mismatch) stay out of the numerator
    but still count in the denominator - one child that no longer has a
    counterpart pulls the score down proportionally rather than vanishing
    from it.
    Details: docs/dev/analysis/composite_matching.md#composite_score
    """
    config = config or ComponentMatchingConfig()
    cache = _cache if _cache is not None else {}
    cache_key = (container_a.id, container_b.id)
    if cache_key in cache:
        return cache[cache_key]

    root_similarity = cosine_similarity(
        container_root_vector(container_a, config), container_root_vector(container_b, config)
    )

    pair_similarity: Dict[Tuple[int, int], float] = {}
    cost_matrix: List[List[float]] = []
    for i, child_a in enumerate(container_a.children):
        row = []
        for j, child_b in enumerate(container_b.children):
            similarity = _child_similarity(child_a, child_b, geometry_buckets, config, cache)
            pair_similarity[(i, j)] = similarity
            row.append(-similarity)  # min_cost_assignment minimizes cost
        cost_matrix.append(row)

    matched_pairs = tuple(min_cost_assignment(cost_matrix)) if cost_matrix else ()
    matched_similarity_sum = sum(pair_similarity[pair] for pair in matched_pairs)

    children_a, children_b = len(container_a.children), len(container_b.children)
    score = (root_similarity + matched_similarity_sum) / (1 + max(children_a, children_b))
    full_coverage = len(matched_pairs) == children_a == children_b

    result = CompositeMatchResult(
        root_similarity=root_similarity, matched_pairs=matched_pairs, score=score, full_coverage=full_coverage,
    )
    cache[cache_key] = result
    return result


def _child_similarity(
    child_a: Union[ContainerNode, Dict[str, Any]],
    child_b: Union[ContainerNode, Dict[str, Any]],
    geometry_buckets: GeometryBuckets,
    config: ComponentMatchingConfig,
    cache: Dict[Tuple[str, str], CompositeMatchResult],
) -> float:
    a_is_container = isinstance(child_a, ContainerNode)
    b_is_container = isinstance(child_b, ContainerNode)
    if a_is_container != b_is_container:
        return 0.0  # a leaf component can never match a composite root
    if a_is_container:
        return composite_score(child_a, child_b, geometry_buckets, config, cache).score
    return cosine_similarity(
        leaf_feature_vector(child_a, geometry_buckets, config),
        leaf_feature_vector(child_b, geometry_buckets, config),
    )


def classify_composite_match(result: CompositeMatchResult, config: Optional[ComponentMatchingConfig] = None) -> str:
    """`"exact"`, `"family"`, or `"none"` - the tiers issue #132 defines,
    at the thresholds issue #133 calibrated. The exact tier is a hard
    gate (`result.full_coverage`) **and** a threshold, not a threshold
    alone: a composite with unmatched children is capped at family tier
    regardless of how high its coverage-weighted score computes.
    Details: docs/dev/analysis/composite_matching.md#classify_composite_match
    """
    thresholds = (config or ComponentMatchingConfig()).thresholds
    if result.full_coverage and result.score >= thresholds.composite_exact:
        return "exact"
    if result.score >= thresholds.composite_family:
        return "family"
    return "none"
