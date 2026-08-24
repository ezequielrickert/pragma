"""Live CSS preview boxes for component catalog variants - real inline
styles from captured per-instance facts, never a screenshot (ticket #182).

Placement in the dashboard shell (catalog page, graph detail, or both) is
decided by the shared redesign; this module only knows how to render one
variant as HTML any consumer can embed.
Details: docs/dev/dashboard/component_preview.md#module
"""
from __future__ import annotations

from html import escape

_PREVIEW_TAGS = frozenset({"button", "a", "input", "select", "textarea", "div", "span"})


def _style_fragment(name: str, value: str) -> str:
    return f"{name}: {value}; " if value else ""


def render_component_variant_preview(
    tag: str,
    *,
    text: str,
    color: str = "",
    background_color: str = "",
    font_size: str = "",
    font_weight: str = "",
    width: str = "",
    height: str = "",
    border_radius: str = "",
    border_color: str = "",
    border_width: str = "",
    box_shadow: str = "",
    display: str = "inline-flex",
) -> str:
    """One real element with inline CSS from observed style facts.
    Details: docs/dev/dashboard/component_preview.md#render_component_variant_preview
    """
    safe_tag = tag if tag in _PREVIEW_TAGS else "div"
    style = "".join(
        part for part in (
            _style_fragment("color", color),
            _style_fragment("background-color", background_color),
            _style_fragment("font-size", font_size),
            _style_fragment("font-weight", font_weight),
            _style_fragment("width", width),
            _style_fragment("height", height),
            _style_fragment("border-radius", border_radius),
            _style_fragment("border-color", border_color),
            _style_fragment("border-width", border_width),
            _style_fragment("border-style", "solid" if border_width else ""),
            _style_fragment("box-shadow", box_shadow),
            _style_fragment("display", display),
            _style_fragment("align-items", "center"),
            _style_fragment("justify-content", "center"),
            _style_fragment("padding", "0 12px"),
            _style_fragment("box-sizing", "border-box"),
            _style_fragment("overflow", "hidden"),
            _style_fragment("text-decoration", "none" if safe_tag == "a" else ""),
        )
        if part
    )
    label = escape(text or safe_tag)
    if safe_tag == "input":
        return (
            f'<div class="component-preview">'
            f'<input type="text" style="{escape(style)}" value="{label}" aria-hidden="true" readonly />'
            f"</div>"
        )
    return (
        f'<div class="component-preview">'
        f'<{safe_tag} style="{escape(style)}" aria-hidden="true">{label}</{safe_tag}>'
        f"</div>"
    )
