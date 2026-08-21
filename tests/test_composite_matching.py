"""Unit tests for composite_matching.py - hand-built ContainerNode trees,
same convention as tests/test_component_family.py's inline component dicts.
"""
from analysis.component_matching_config import ComponentMatchingConfig
from analysis.composite_matching import (
    ContainerNode,
    bucket_candidates,
    classify_composite_match,
    composite_score,
    container_root_vector,
)
from analysis.leaf_feature_vector import compute_geometry_buckets


def _link(text, href):
    return {"tag": "a", "component_type": "link", "text": text, "href": href}


def _nav(node_id, links, css_class="nav", landmark="navigation"):
    return ContainerNode(id=node_id, tag="nav", role="navigation", landmark=landmark, css_class=css_class,
                          children=[_link(f"L{i}", f"/page{i}") for i in links])


_BUCKETS = compute_geometry_buckets([])
_CONFIG = ComponentMatchingConfig()


def test_two_identical_navbars_score_full_coverage_and_classify_exact():
    a = _nav("navA", range(3))
    b = _nav("navB", range(3))

    result = composite_score(a, b, _BUCKETS, _CONFIG)

    assert result.full_coverage is True
    assert len(result.matched_pairs) == 3
    assert classify_composite_match(result, _CONFIG) == "exact"


def test_a_differing_child_count_is_capped_at_family_regardless_of_score():
    a = _nav("navA", range(5))
    b = _nav("navB", range(6))  # one extra link, e.g. a conditional "Admin" entry

    result = composite_score(a, b, _BUCKETS, _CONFIG)

    assert result.full_coverage is False
    assert classify_composite_match(result, _CONFIG) != "exact"


def test_one_differing_child_barely_dents_an_otherwise_identical_navbar():
    """A single page-specific class difference (an "active" marker) is one
    term among many, not a veto - the score stays high."""
    a = ContainerNode(
        id="navA", tag="nav", role="navigation", landmark="navigation", css_class="nav",
        children=[_link("Home", "/"), _link("About", "/about"), _link("Contact", "/contact")],
    )
    b = ContainerNode(
        id="navB", tag="nav", role="navigation", landmark="navigation", css_class="nav",
        children=[
            {**_link("Home", "/"), "css_class": "active"},
            _link("About", "/about"), _link("Contact", "/contact"),
        ],
    )

    result = composite_score(a, b, _BUCKETS, _CONFIG)

    assert result.full_coverage is True
    assert result.score > _CONFIG.thresholds.composite_family


def test_two_unrelated_composites_score_low_and_classify_none():
    nav = _nav("nav", range(3))
    footer = ContainerNode(
        id="footer", tag="footer", role="contentinfo", landmark="contentinfo", css_class="site-footer",
        children=[{"tag": "p", "component_type": "element", "text": "Copyright 2026"}],
    )

    result = composite_score(nav, footer, _BUCKETS, _CONFIG)

    assert classify_composite_match(result, _CONFIG) == "none"


def test_nested_composites_recurse_and_the_result_is_cached():
    inner_a = _nav("innerA", range(2))
    inner_b = _nav("innerB", range(2))
    outer_a = ContainerNode(id="outerA", tag="div", role="", landmark="", css_class="wrap", children=[inner_a])
    outer_b = ContainerNode(id="outerB", tag="div", role="", landmark="", css_class="wrap", children=[inner_b])

    cache = {}
    result = composite_score(outer_a, outer_b, _BUCKETS, _CONFIG, _cache=cache)

    assert result.full_coverage is True
    assert ("innerA", "innerB") in cache  # the nested pair was scored and cached
    assert ("outerA", "outerB") in cache


def test_a_leaf_can_never_match_a_composite_root():
    """A composite with a leaf child compared against one with a nested
    composite child in the same slot must not silently pair them - the
    mismatched-kind pair scores 0 and is only chosen if nothing better
    exists."""
    a = ContainerNode(
        id="a", tag="div", role="", landmark="", css_class="mixed",
        children=[_link("Home", "/"), ContainerNode(id="nestedA", tag="nav", role="navigation")],
    )
    b = ContainerNode(
        id="b", tag="div", role="", landmark="", css_class="mixed",
        children=[_link("Home", "/"), ContainerNode(id="nestedB", tag="nav", role="navigation")],
    )

    result = composite_score(a, b, _BUCKETS, _CONFIG)

    assert result.full_coverage is True
    # The leaf-to-leaf and container-to-container pairs, not a cross-kind one.
    matched_kinds = {(isinstance(a.children[i], ContainerNode), isinstance(b.children[j], ContainerNode))
                      for i, j in result.matched_pairs}
    assert matched_kinds == {(False, False), (True, True)}


def test_container_root_vector_reflects_landmark_and_css_class():
    nav = _nav("nav", range(1), css_class="primary-nav", landmark="navigation")
    banner = ContainerNode(id="banner", tag="header", role="banner", landmark="banner", css_class="site-header")

    nav_vector = container_root_vector(nav, _CONFIG)
    banner_vector = container_root_vector(banner, _CONFIG)

    assert nav_vector != banner_vector


def test_bucket_candidates_groups_by_tag_and_role_and_respects_child_count_slack():
    matching_pair_a = _nav("a1", range(4))
    matching_pair_b = _nav("a2", range(5))  # within 50% slack of 5's larger side
    too_different = _nav("a3", range(20))  # far outside slack
    different_kind = ContainerNode(id="footer", tag="footer", role="contentinfo")

    pairs = bucket_candidates(
        [matching_pair_a, matching_pair_b, too_different, different_kind],
        child_count_slack=_CONFIG.composite_bucketing.child_count_slack,
    )

    pair_ids = {frozenset((p[0].id, p[1].id)) for p in pairs}
    assert frozenset(("a1", "a2")) in pair_ids
    assert frozenset(("a1", "a3")) not in pair_ids
    assert all("footer" not in pair for pair in pair_ids)
