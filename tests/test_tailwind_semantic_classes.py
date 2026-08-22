"""Unit tests for tailwind_semantic_classes.py's Tailwind-utility parser -
hand-authored class strings, same convention as
tests/test_leaf_feature_vector.py.
"""
import math

from analysis.tailwind_semantic_classes import TOTAL_DIMS, semantic_css_class_vector


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_vector_length_matches_total_dims():
    assert len(semantic_css_class_vector("bg-white p-4")) == TOTAL_DIMS


def test_empty_css_class_produces_an_all_zero_vector():
    assert semantic_css_class_vector("") == [0.0] * TOTAL_DIMS


def test_identical_class_strings_produce_the_same_vector():
    one = semantic_css_class_vector("bg-white border-3 rounded-xl p-4")
    other = semantic_css_class_vector("bg-white border-3 rounded-xl p-4")
    assert one == other


def test_a_custom_color_variant_reads_as_family_close_but_not_identical():
    """The doctor-listing-card pattern (#164/#168): two shells sharing
    every layout/spacing/border/shadow class, differing only by a
    theme-specific color modifier (`border-extra-N`, this repo's own
    per-doctor badge color, not one of Tailwind's default palettes) -
    same family, not a coin-flip collision, not an exact duplicate.
    """
    shell = "bg-white shadow-soft border-3 relative rounded-xl p-4 w-full flex flex-col"
    variant_a = semantic_css_class_vector(f"{shell} border-extra-6")
    variant_b = semantic_css_class_vector(f"{shell} border-extra-2")
    identical = semantic_css_class_vector(f"{shell} border-extra-6")

    same_family_similarity = _cosine(variant_a, variant_b)
    assert 0.8 < same_family_similarity < 1.0
    assert math.isclose(_cosine(variant_a, identical), 1.0)


def test_a_known_tailwind_palette_shade_step_reads_as_closer_than_a_different_family():
    """`blue-500` vs `blue-600` (one shade step, same family) should read
    as more similar than `blue-500` vs `red-500` (same shade step, a
    different family entirely) - the shade scalar only applies to
    Tailwind's own default palette names, where a numeric step actually
    means "one perceptual shade darker."
    """
    base = semantic_css_class_vector("bg-blue-500")
    one_step_darker = semantic_css_class_vector("bg-blue-600")
    different_family = semantic_css_class_vector("bg-red-500")

    assert _cosine(base, one_step_darker) > _cosine(base, different_family)


def test_border_width_is_not_misclassified_as_a_color_variant():
    """`border-3` (a width utility) must land in the border concept, not
    color - `border`/`divide` are color-capable prefixes too, so the
    parser has to disambiguate a numeric/side/style suffix from an actual
    color name before routing the token.
    """
    only_width = semantic_css_class_vector("border-3")
    only_color = semantic_css_class_vector("border-red-500")
    assert only_width != only_color

    # Border block (concept 4 of 6: color, spacing, typography, border,
    # shadow, layout) is nonzero for the width utility...
    from analysis.tailwind_semantic_classes import COLOR_DIMS, SPACING_DIMS, TYPOGRAPHY_DIMS, BORDER_DIMS

    border_start = COLOR_DIMS + SPACING_DIMS + TYPOGRAPHY_DIMS
    border_end = border_start + BORDER_DIMS
    assert any(only_width[border_start:border_end])
    # ...and the color block (concept 1) is nonzero for the color one.
    assert any(only_color[:COLOR_DIMS])


def test_state_variant_prefix_does_not_change_the_base_concept():
    """`hover:shadow-2xl` still expresses a shadow, just conditionally -
    the condition itself isn't a design property this parser tracks."""
    plain = semantic_css_class_vector("shadow-2xl")
    hovered = semantic_css_class_vector("hover:shadow-2xl")
    assert plain == hovered


def test_an_unrecognized_token_still_contributes_signal_via_the_layout_catch_all():
    """Absence-as-signal, same precedent as leaf_feature_vector.py's hash
    blocks: an unmatched token isn't dropped, it lands in layout's hash."""
    assert semantic_css_class_vector("some-unknown-utility") != [0.0] * TOTAL_DIMS


def test_spacing_scale_distinguishes_padding_values():
    tight = semantic_css_class_vector("p-1")
    loose = semantic_css_class_vector("p-8")
    identical_shell = semantic_css_class_vector("p-1")
    assert tight != loose
    assert tight == identical_shell


def test_layout_and_typography_tokens_land_in_different_concepts():
    layout_only = semantic_css_class_vector("flex w-full")
    typography_only = semantic_css_class_vector("text-lg font-bold")
    assert layout_only != typography_only
