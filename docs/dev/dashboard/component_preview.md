# `dashboard/component_preview.py`

## module

Renders one component variant as a live CSS box using real captured style facts (color,
background, typography, border, shadow, size, text) - never a screenshot. Ticket #182 builds
this renderer; where it embeds in the dashboard shell is a separate placement decision.

## render_component_variant_preview

Returns a small HTML fragment: a `.component-preview` wrapper around a real element (`button`,
`a`, `input`, ...) with inline `style` built only from the passed facts. Empty facts are omitted
rather than inventing defaults beyond layout helpers (`inline-flex`, padding).
