"""Unit tests for the design-token document and its colour maths
(generators/design_tokens.py, color_space.py)."""
import json

from generators.color_space import (
    JUST_NOTICEABLE_DIFFERENCE,
    parse_css_color,
    perceptual_distance,
    to_hex,
    to_lab,
)
from generators.design_tokens import build_color_tokens, build_type_tokens


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


# --- the DTCG source document ---

def _request(component=None, state_styles=()):
    from core.documents import DocumentRequest

    class _Store:
        def get_component_ledger(self):
            return {"shop/": {"a": component or _component()}}

        def get_state_styles(self):
            return list(state_styles)

    return DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)


def _outputs(request):
    from generators.design_tokens import DesignTokensDocument

    return DesignTokensDocument().outputs(request)


def test_generate_returns_a_json_source_and_a_markdown_view():
    outputs = _outputs(_request())

    assert [o.filename for o in outputs] == ["tokens", "tokens"]
    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_the_source_document_validates_as_dtcg_and_carries_pragma_extensions():
    outputs = _outputs(_request(component=_component(color="rgb(45, 119, 55)")))

    document = json.loads(outputs[0].content)

    color_token = document["core"]["color"]["text-1"]
    assert color_token["$type"] == "color"
    assert color_token["$value"] == "#2d7737"
    frequency = color_token["$extensions"]["pragma"]["usage_frequency"]
    assert frequency == {"count": 1, "is_system_candidate": False}
    assert document["semantic"] == {}


def test_source_is_reserved_not_invented():
    outputs = _outputs(_request())

    document = json.loads(outputs[0].content)
    token = document["core"]["color"]["text-1"]

    assert token["$extensions"]["pragma"]["source"] == {
        "stylesheets": [], "css_variables": [], "selectors": [], "inline_style_count": 0,
    }


def test_a_token_used_three_or_more_times_is_a_system_candidate():
    components = [_component(color="rgb(45, 119, 55)")] * 3
    from generators.design_tokens import build_tokens_document

    document = build_tokens_document(_MultiComponentStore(components))
    token = next(iter(document["core"]["color"].values()))

    assert token["$extensions"]["pragma"]["usage_frequency"] == {"count": 3, "is_system_candidate": True}


class _MultiComponentStore:
    def __init__(self, components):
        self._components = components

    def get_component_ledger(self):
        return {"shop/": {str(i): c for i, c in enumerate(self._components)}}

    def get_state_styles(self):
        return []


def test_the_document_says_its_names_are_positional_not_semantic():
    """Naming a colour `brand-primary` would be a guess presented as fact."""
    view = _outputs(_request())[1].content

    assert "positional" in view
    assert "would be a guess" in view


def test_the_document_explains_why_spacing_is_absent():
    """Absent because the crawl measures at 800x600, not because nobody
    thought of it - and a reader should be able to tell those apart."""
    view = _outputs(_request())[1].content

    assert "**Spacing is absent.**" in view
    assert "800x600" in view


def test_a_non_color_state_token_uses_its_own_css_property_as_the_dtcg_type():
    outputs = _outputs(_request(state_styles=[
        {"page_url": "shop/", "path": "a", "state": "focus", "property": "outline", "value": "2px solid #fc0"},
    ]))
    document = json.loads(outputs[0].content)

    token = next(iter(document["core"]["interaction-state"].values()))
    assert token["$type"] == "outline"
    assert token["$value"] == "2px solid #fc0"


def test_declared_hover_values_become_state_tokens():
    from generators.design_tokens import build_state_tokens

    tokens = build_state_tokens([
        {"page_url": "p", "path": "a", "state": "hover", "property": "color", "value": "#1a4f9c"},
        {"page_url": "p", "path": "b", "state": "hover", "property": "color", "value": "#1a4f9c"},
    ])

    assert len(tokens) == 1
    assert (tokens[0].state, tokens[0].value, tokens[0].usage_count) == ("hover", "#1a4f9c", 2)


def test_hover_and_focus_are_separate_tokens():
    from generators.design_tokens import build_state_tokens

    tokens = build_state_tokens([
        {"page_url": "p", "path": "a", "state": "hover", "property": "color", "value": "#111"},
        {"page_url": "p", "path": "a", "state": "focus", "property": "outline", "value": "2px solid"},
    ])

    assert {t.state for t in tokens} == {"focus", "hover"}


def test_an_incomplete_state_row_is_dropped():
    """A declaration with no value is not a token."""
    from generators.design_tokens import build_state_tokens

    assert build_state_tokens([
        {"page_url": "p", "path": "a", "state": "hover", "property": "color", "value": ""}
    ]) == []


def test_the_states_section_explains_a_cross_origin_shortfall():
    """Absent must not read as "this site declares no hover styles" -
    the section (and its caveat) renders even with zero states captured."""
    view = _outputs(_request())[1].content

    assert "## Interaction State" in view
    assert "cross-origin" in view


def test_recorded_states_reach_the_view_document():
    view = _outputs(_request(state_styles=[
        {"page_url": "shop/", "path": "a", "state": "hover", "property": "background-color", "value": "#1a4f9c"},
    ]))[1].content

    assert "`#1a4f9c`" in view
    assert "background-color" in view
