"""Unit tests for component_family.py's pure clustering logic."""
from generators.component_family import (
    ComponentFamily,
    build_component_families,
    label_for_tag,
    tags_with_multiple_instances,
)


def _comp(page_url, path, tag, component_type, css_class):
    return {"page_url": page_url, "path": path, "tag": tag, "component_type": component_type, "css_class": css_class}


def test_two_identical_buttons_form_a_family():
    components = [
        _comp("p1", "btn1", "button", "submit button", "btn btn-primary"),
        _comp("p1", "btn2", "button", "submit button", "btn btn-primary"),
    ]
    families = build_component_families(components)
    assert len(families) == 1
    assert families[0].tag == "button"
    assert families[0].common_classes == ("btn", "btn-primary")
    assert set(families[0].member_paths) == {("p1", "btn1"), ("p1", "btn2")}


def test_color_variant_still_counts_as_the_same_family():
    # Shares 2 of 3 classes (50%) - a color-modifier difference, exactly
    # the "same button, different variant" case this feature exists for.
    components = [
        _comp("p1", "btn1", "button", "submit button", "btn btn-primary rounded"),
        _comp("p1", "btn2", "button", "submit button", "btn btn-secondary rounded"),
    ]
    families = build_component_families(components)
    assert len(families) == 1
    assert families[0].common_classes == ("btn", "rounded")


def test_a_single_component_does_not_form_a_family():
    components = [_comp("p1", "btn1", "button", "submit button", "btn btn-primary")]
    assert build_component_families(components) == []


def test_different_component_type_never_merges_even_with_identical_classes():
    # Same tag, same classes, different component_type (e.g. one is a
    # native <select>-driven dropdown fact, the other a plain button) -
    # must never share a family; the bucket boundary is absolute.
    components = [
        _comp("p1", "a1", "button", "submit button", "btn"),
        _comp("p1", "a2", "button", "toggle switch", "btn"),
    ]
    assert build_component_families(components) == []


def test_dissimilar_classes_do_not_merge():
    components = [
        _comp("p1", "a1", "button", "button", "btn btn-primary"),
        _comp("p1", "a2", "button", "button", "nav-link footer-icon"),
    ]
    assert build_component_families(components) == []


def test_two_unstyled_components_of_the_same_kind_still_form_a_family():
    components = [
        _comp("p1", "a1", "button", "button", ""),
        _comp("p1", "a2", "button", "button", ""),
    ]
    families = build_component_families(components)
    assert len(families) == 1
    assert families[0].common_classes == ()


def test_unstyled_and_styled_component_never_merge():
    components = [
        _comp("p1", "a1", "button", "button", ""),
        _comp("p1", "a2", "button", "button", "btn"),
    ]
    assert build_component_families(components) == []


def test_components_without_a_tag_are_skipped_not_errored():
    components = [
        _comp("p1", "a1", "", "element", "btn"),
        _comp("p1", "a2", "", "element", "btn"),
    ]
    assert build_component_families(components) == []


def test_three_way_family_reports_every_member():
    components = [
        _comp("p1", "a1", "button", "button", "btn btn-primary"),
        _comp("p1", "a2", "button", "button", "btn btn-primary"),
        _comp("p2", "a3", "button", "button", "btn btn-primary"),
    ]
    families = build_component_families(components)
    assert len(families) == 1
    assert len(families[0].member_paths) == 3


def test_label_for_tag_maps_anchor_to_link():
    assert label_for_tag("a") == "Link"


def test_label_for_tag_capitalizes_plain_tags():
    assert label_for_tag("button") == "Button"
    assert label_for_tag("select") == "Select"


def test_label_for_tag_falls_back_to_component_for_unsafe_names():
    # A custom element's hyphen isn't valid in an unescaped Cypher label.
    assert label_for_tag("my-widget") == "Component"
    assert label_for_tag("") == "Component"


def test_tags_with_multiple_instances_requires_at_least_two():
    components = [
        _comp("p1", "a1", "button", "button", ""),
        _comp("p1", "a2", "button", "button", ""),
        _comp("p1", "a3", "input", "text field (text)", ""),
    ]
    assert tags_with_multiple_instances(components) == {"button"}


def test_component_family_dataclass_is_hashable_and_comparable():
    # Frozen + tuple fields (not list) so callers can put families in a
    # set or use them as dict keys without a TypeError.
    fam = ComponentFamily(tag="button", component_type="button", common_classes=("btn",), member_paths=(("p1", "a1"),))
    assert fam == ComponentFamily(tag="button", component_type="button", common_classes=("btn",), member_paths=(("p1", "a1"),))
    {fam}  # must not raise
