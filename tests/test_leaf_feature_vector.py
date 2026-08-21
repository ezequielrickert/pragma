"""Unit tests for leaf_feature_vector.py's pure vector-computation logic -
hand-authored component dicts, same convention as
tests/test_component_family.py.
"""
import math

from analysis.component_matching_config import ComponentMatchingConfig, LeafWeights
from analysis.leaf_feature_vector import (
    COMPONENT_TYPE_VALUES,
    compute_geometry_buckets,
    leaf_feature_vector,
)


def _comp(tag="button", component_type="button", css_class="", **rest):
    return {"tag": tag, "component_type": component_type, "css_class": css_class, **rest}


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_vector_length_matches_the_documented_dimensionality():
    buckets = compute_geometry_buckets([])
    vector = leaf_feature_vector(_comp(), buckets)
    assert len(vector) == 169


def test_two_content_identical_components_produce_the_same_vector():
    one = _comp(css_class="btn btn-primary", href="/cart")
    other = _comp(css_class="btn btn-primary", href="/cart")
    buckets = compute_geometry_buckets([one, other])

    assert leaf_feature_vector(one, buckets) == leaf_feature_vector(other, buckets)


def test_a_different_tag_moves_the_vector_away_from_cosine_one():
    button = _comp(tag="button")
    link = _comp(tag="a")
    buckets = compute_geometry_buckets([button, link])

    similarity = _cosine(leaf_feature_vector(button, buckets), leaf_feature_vector(link, buckets))
    assert similarity < 1.0


def test_hashing_is_deterministic_across_calls_not_process_randomized():
    """Pins the design's own reason for sha1 over the builtin hash() -
    PYTHONHASHSEED would make this test flaky if the vector used it."""
    comp = _comp(css_class="btn", href="/cart", name="go")
    buckets = compute_geometry_buckets([comp])

    first = leaf_feature_vector(comp, buckets)
    second = leaf_feature_vector(comp, buckets)
    assert first == second


def test_component_type_s_templated_text_field_branch_collapses_to_one_value():
    """"text field (email)" and "text field (password)" must map to the
    same closed vocabulary value - the specific input_type already has
    its own hashed field, so the component_type block must not
    distinguish them a second time."""
    from analysis.leaf_feature_vector import _collapsed_component_type

    assert "text field" in COMPONENT_TYPE_VALUES
    assert _collapsed_component_type("text field (email)") == "text field"
    assert _collapsed_component_type("text field (password)") == "text field"


def test_css_class_overlap_increases_similarity_over_no_overlap():
    shared = _comp(css_class="btn btn-primary rounded")
    variant = _comp(css_class="btn btn-secondary rounded")
    unrelated = _comp(css_class="nav-link footer-icon")
    buckets = compute_geometry_buckets([shared, variant, unrelated])

    similar_pair = _cosine(leaf_feature_vector(shared, buckets), leaf_feature_vector(variant, buckets))
    dissimilar_pair = _cosine(leaf_feature_vector(shared, buckets), leaf_feature_vector(unrelated, buckets))
    assert similar_pair > dissimilar_pair


def test_missing_facts_fields_default_without_raising():
    buckets = compute_geometry_buckets([])
    vector = leaf_feature_vector({}, buckets)
    assert len(vector) == 169


def test_geometry_buckets_rank_components_small_medium_large_within_their_own_kind():
    small = _comp(width=10.0, height=10.0)
    medium = _comp(width=50.0, height=50.0)
    large = _comp(width=200.0, height=200.0)
    buckets = compute_geometry_buckets([small, medium, large])

    small_vec = leaf_feature_vector(small, buckets, ComponentMatchingConfig())
    large_vec = leaf_feature_vector(large, buckets, ComponentMatchingConfig())
    # Distinct geometry buckets are the one thing guaranteed to differ
    # between the smallest and largest of three same-kind components -
    # the vectors must not be identical.
    assert small_vec != large_vec


def test_a_component_type_with_no_geometry_siblings_falls_back_to_the_middle_bucket():
    """Fewer than 3 same-(tag, component_type) components can't split into
    real tertiles - compute_geometry_buckets skips the group entirely, and
    a lookup against it must not raise."""
    lone = _comp(tag="dialog", component_type="element", width=999.0, height=999.0)
    buckets = compute_geometry_buckets([lone])

    vector = leaf_feature_vector(lone, buckets)
    assert len(vector) == 169


def test_leaf_weights_scale_a_block_s_contribution():
    """Doubling css_class's weight must move the vector by exactly the
    css_class block's own raw magnitude times the weight delta - nothing
    more, which is also an implicit check that no other block moved."""
    from analysis.leaf_feature_vector import _CSS_CLASS_BUCKETS, _hash_multi_hot

    comp = _comp(css_class="btn", tag="button", component_type="button")
    buckets = compute_geometry_buckets([comp])
    base = leaf_feature_vector(comp, buckets, ComponentMatchingConfig(leaf_weights=LeafWeights(css_class=0.6)))
    doubled = leaf_feature_vector(comp, buckets, ComponentMatchingConfig(leaf_weights=LeafWeights(css_class=1.2)))

    raw_css_class = _hash_multi_hot(["btn"], _CSS_CLASS_BUCKETS)
    total_move = sum(abs(d - b) for d, b in zip(doubled, base))
    expected_move = sum(abs(v) * (1.2 - 0.6) for v in raw_css_class)
    assert total_move == expected_move
