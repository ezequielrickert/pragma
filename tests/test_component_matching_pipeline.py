"""Regression coverage for `analysis/component_matching_pipeline.py`'s
sub-clustering pass (`_subgroup_leaf_vectors`, wired into
`_build_leaf_families`) - issue #171.

Members below differ by `css_class` (the vector's most heavily weighted
block, `leaf_weights.css_class`) rather than a raw color field: two Tailwind
utility strings that read as genuinely different design concepts (a filled
blue button vs. a bordered white one) are what actually pushes cosine
similarity below `thresholds.leaf_subgroup` in this vector's real geometry -
a smaller, single-field difference doesn't move it enough to be a reliable
regression signal. `_build_leaf_families` bucketing groups purely by
`(tag, component_type)`; every member below shares both on purpose, so
`css_class` is what has to carry each test's story.
"""
from analysis.component_matching_config import ComponentMatchingConfig
from analysis.component_matching_pipeline import _build_leaf_families, _subgroup_leaf_vectors
from analysis.leaf_feature_vector import compute_geometry_buckets, leaf_feature_vector

_FILLED_BLUE = "bg-blue-500 text-white rounded-md"
_BORDERED_WHITE = "bg-white text-black border border-gray-300"


def _component(path: str, css_class: str, page_url: str = "https://x/a") -> dict[str, str]:
    return {
        "id": f"component:{path}", "page_url": page_url, "path": path,
        "tag": "button", "component_type": "button", "css_class": css_class,
    }


def _vectors(members):
    config = ComponentMatchingConfig()
    geometry_buckets = compute_geometry_buckets(members)
    return config, [leaf_feature_vector(m, geometry_buckets, config) for m in members]


def test_two_visually_distinct_variants_land_in_two_sub_clusters():
    filled = [_component("btn-1", _FILLED_BLUE), _component("btn-2", _FILLED_BLUE)]
    bordered = [_component("btn-3", _BORDERED_WHITE), _component("btn-4", _BORDERED_WHITE)]
    members = filled + bordered
    config, vectors = _vectors(members)

    subgroups = _subgroup_leaf_vectors(members, vectors, config.thresholds.leaf_subgroup)

    filled_paths = frozenset({("https://x/a", "btn-1"), ("https://x/a", "btn-2")})
    bordered_paths = frozenset({("https://x/a", "btn-3"), ("https://x/a", "btn-4")})
    assert {frozenset(group) for group in subgroups} == {filled_paths, bordered_paths}


def test_every_member_lands_in_exactly_one_sub_cluster_including_an_outlier():
    members = [
        _component("btn-1", _FILLED_BLUE), _component("btn-2", _FILLED_BLUE),
        _component("btn-3", _BORDERED_WHITE),  # the family's one odd-one-out
    ]
    config, vectors = _vectors(members)

    subgroups = _subgroup_leaf_vectors(members, vectors, config.thresholds.leaf_subgroup)

    every_path = {path for group in subgroups for path in group}
    assert every_path == {("https://x/a", m["path"]) for m in members}
    assert any(len(group) == 1 for group in subgroups)


def test_a_uniform_family_comes_back_as_one_sub_cluster():
    members = [_component(f"btn-{i}", _FILLED_BLUE) for i in range(3)]
    config, vectors = _vectors(members)

    subgroups = _subgroup_leaf_vectors(members, vectors, config.thresholds.leaf_subgroup)

    assert subgroups == (tuple(sorted(("https://x/a", m["path"]) for m in members)),)


def test_build_leaf_families_fills_in_subgroups_for_each_family():
    # A closer pair than `_FILLED_BLUE`/`_BORDERED_WHITE` - similar enough
    # to stay one family (>= thresholds.leaf_family) while still landing
    # below thresholds.leaf_subgroup, so this exercises the sub-cluster
    # pass finding a split *inside* an already-formed family, not
    # `_build_leaf_families`'s own bucketing splitting them apart first.
    padded = "bg-blue-500 text-white rounded-md px-4 py-2"
    bordered = "bg-blue-500 text-white rounded-md border border-gray-300"
    components = [
        _component("btn-1", padded), _component("btn-2", padded),
        _component("btn-3", bordered), _component("btn-4", bordered),
    ]
    for i, component in enumerate(components):
        component["id"] = f"component:{i}"  # four distinct canonical components, one family
    config = ComponentMatchingConfig()
    geometry_buckets = compute_geometry_buckets(components)

    families = _build_leaf_families(components, geometry_buckets, config)

    assert len(families) == 1
    subgroups = families[0].subgroups
    assert len(subgroups) == 2
    assert sum(len(group) for group in subgroups) == 4
