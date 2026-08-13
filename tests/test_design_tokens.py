"""Unit tests for the design-token document and its colour maths
(src/generators/design_tokens.py, color_space.py)."""
import json

from src.generators.color_space import (
    JUST_NOTICEABLE_DIFFERENCE,
    parse_css_color,
    perceptual_distance,
    to_hex,
    to_lab,
)
from src.generators.design_tokens import build_color_tokens, build_type_tokens


def _component(color="rgb(0, 0, 0)", background="rgb(255, 255, 255)", size="16px", weight="400"):
    return {
        "page_url": "shop/", "path": "a", "color": color, "background_color": background,
        "font_size": size, "font_weight": weight,
    }


# --- colour parsing ---

def test_computed_rgb_and_rgba_are_both_parsed():
    assert parse_css_color("rgb(45, 119, 55)") == (45, 119, 55)
    assert parse_css_color("rgba(45, 119, 55, 0.5)") == (45, 119, 55)


def test_a_fully_transparent_colour_is_not_a_colour():
    """rgba(0,0,0,0) is what an element with no background of its own
    reports - treating it as black would put an invisible black at the top
    of every palette."""
    assert parse_css_color("rgba(0, 0, 0, 0)") is None


def test_an_unparseable_value_is_none_not_a_crash():
    assert parse_css_color("") is None
    assert parse_css_color("inherit") is None


def test_hex_output_is_what_a_design_tool_expects():
    assert to_hex((45, 119, 55)) == "#2d7737"


# --- perceptual distance ---

def test_black_and_white_are_a_full_lightness_range_apart():
    assert round(perceptual_distance((0, 0, 0), (255, 255, 255)), 1) == 100.0


def test_lab_lightness_is_zero_for_black_and_one_hundred_for_white():
    assert round(to_lab((0, 0, 0))[0], 1) == 0.0
    assert round(to_lab((255, 255, 255))[0], 1) == 100.0


def test_two_near_identical_greys_are_below_the_noticeable_threshold():
    assert perceptual_distance((240, 240, 240), (241, 241, 241)) < JUST_NOTICEABLE_DIFFERENCE


def test_distance_is_symmetric():
    a, b = (12, 34, 56), (200, 100, 50)
    assert round(perceptual_distance(a, b), 6) == round(perceptual_distance(b, a), 6)


# --- clustering ---

def test_near_identical_colours_collapse_into_one_token():
    """A real application's computed styles hold dozens of near-identical
    greys; listing all of them is a dump, not a palette."""
    components = [_component(color="rgb(240, 240, 240)")] * 3 + [_component(color="rgb(241, 241, 241)")]

    text_tokens = [t for t in build_color_tokens(components) if t.role == "text"]

    assert len(text_tokens) == 1
    assert text_tokens[0].usage_count == 4
    assert text_tokens[0].merged_from == ("#f1f1f1",)


def test_the_most_used_colour_wins_its_cluster():
    """The winner is what a design system would keep."""
    components = [_component(color="rgb(240, 240, 240)")] * 5 + [_component(color="rgb(241, 241, 241)")]

    token = next(t for t in build_color_tokens(components) if t.role == "text")

    assert token.value == "#f0f0f0"


def test_visibly_different_colours_stay_apart():
    components = [_component(color="rgb(0, 0, 0)"), _component(color="rgb(200, 30, 30)")]

    assert len([t for t in build_color_tokens(components) if t.role == "text"]) == 2


def test_text_and_surface_colours_are_separate_tokens_even_at_the_same_value():
    """The same value used for text and as a surface is two tokens in any
    design system."""
    tokens = build_color_tokens([_component(color="rgb(20, 20, 20)", background="rgb(20, 20, 20)")])

    assert {t.role for t in tokens} == {"text", "surface"}
    assert len({t.name for t in tokens}) == 2


def test_tokens_are_ranked_by_use():
    components = [_component(color="rgb(10, 10, 10)")] + [_component(color="rgb(200, 30, 30)")] * 4

    text_tokens = [t for t in build_color_tokens(components) if t.role == "text"]

    assert text_tokens[0].value == "#c81e1e"
    assert text_tokens[0].name == "text-1"


# --- type scale ---

def test_distinct_size_and_weight_pairs_become_steps():
    components = [_component(size="16px", weight="400"), _component(size="16px", weight="700")]

    assert len(build_type_tokens(components)) == 2


def test_steps_are_ordered_largest_first():
    components = [_component(size="12px"), _component(size="32px"), _component(size="16px")]

    assert [t.font_size for t in build_type_tokens(components)] == ["32px", "16px", "12px"]


def test_a_non_pixel_size_sorts_last_instead_of_crashing():
    components = [_component(size="1.5rem"), _component(size="16px")]

    assert [t.font_size for t in build_type_tokens(components)] == ["16px", "1.5rem"]


def test_components_with_no_font_size_are_skipped():
    assert build_type_tokens([_component(size="")]) == []


# --- documents ---

def test_the_document_says_its_names_are_positional_not_semantic():
    """Naming a colour `brand-primary` would be a guess presented as fact."""
    from src.core.documents import DocumentRequest
    from src.generators.design_tokens import DesignTokensDocument

    class _Store:
        def get_component_ledger(self, site):
            return {"shop/": {"a": _component()}}

        def get_page_measurements(self, site):
            return {}

    text = DesignTokensDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "positional" in text
    assert "would be a guess" in text


def test_the_document_explains_why_spacing_is_absent():
    """Absent because the crawl measures at 800x600, not because nobody
    thought of it - and a reader should be able to tell those apart."""
    from src.core.documents import DocumentRequest
    from src.generators.design_tokens import DesignTokensDocument

    class _Store:
        def get_component_ledger(self, site):
            return {"shop/": {"a": _component()}}

        def get_page_measurements(self, site):
            return {}

    text = DesignTokensDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "Spacing tokens are absent" in text
    assert "800x600" in text


def test_the_json_document_is_parseable():
    from src.core.documents import DocumentRequest
    from src.generators.design_tokens import DesignTokensData

    class _Store:
        def get_component_ledger(self, site):
            return {"shop/": {"a": _component(color="rgb(45, 119, 55)")}}

        def get_page_measurements(self, site):
            return {}

    payload = json.loads(
        DesignTokensData().generate(DocumentRequest(graph_store=_Store(), site="shop.example", agent=None))
    )

    assert payload["spacing"]["absent"] is True
    assert any(token["value"] == "#2d7737" for token in payload["color"])


# --- interaction states (Fase 8) ---

def _pseudo(path="a", states=None):
    return {"path": path, "states": states or {"hover": {"background-color": "#1a4f9c"}}}


def test_declared_hover_values_become_state_tokens():
    from src.generators.design_tokens import build_state_tokens

    tokens = build_state_tokens({"p": {"pseudo_styles": [_pseudo(), _pseudo("b")]}})

    assert len(tokens) == 1
    assert tokens[0].state == "hover"
    assert tokens[0].value == "#1a4f9c"
    assert tokens[0].usage_count == 2


def test_hover_and_focus_are_separate_tokens():
    from src.generators.design_tokens import build_state_tokens

    tokens = build_state_tokens({
        "p": {"pseudo_styles": [_pseudo(states={
            "hover": {"background-color": "#1a4f9c"},
            "focus": {"outline": "2px solid #fc0"},
        })]}
    })

    assert {t.state for t in tokens} == {"focus", "hover"}


def test_no_measurement_pass_means_no_state_tokens():
    from src.generators.design_tokens import build_state_tokens

    assert build_state_tokens({}) == []


def test_the_document_explains_why_state_styles_may_be_missing():
    """Cross-origin stylesheets cannot be read, and a reader has to be able
    to tell that from "this site declares no hover styles"."""
    from src.core.documents import DocumentRequest
    from src.generators.design_tokens import DesignTokensDocument

    class _Store:
        def get_component_ledger(self, site):
            return {"shop/": {"a": _component()}}

        def get_page_measurements(self, site):
            return {}

    text = DesignTokensDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "cross-origin" in text
