"""Unit tests for dashboard/component_preview.py."""
from dashboard.component_preview import render_component_variant_preview


def test_render_component_variant_preview_uses_real_inline_styles():
    html = render_component_variant_preview(
        "button",
        text="Comprar",
        color="rgb(255, 255, 255)",
        background_color="rgb(0, 100, 200)",
        font_size="16px",
        font_weight="700",
        width="120px",
        height="40px",
        border_radius="8px",
        border_color="rgb(0, 80, 160)",
        border_width="1px",
        box_shadow="0 2px 4px rgba(0,0,0,0.2)",
    )

    assert 'class="component-preview"' in html
    assert "<button" in html
    assert "Comprar" in html
    assert "background-color: rgb(0, 100, 200);" in html
    assert "border-radius: 8px;" in html
    assert "box-shadow: 0 2px 4px rgba(0,0,0,0.2);" in html


def test_render_component_variant_preview_omits_empty_style_properties():
    html = render_component_variant_preview("button", text="Go")

    assert "border-radius:" not in html
    assert "box-shadow:" not in html
