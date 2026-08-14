"""Pure mapping helpers: raw JS-discovered component dicts -> the facts
GraphStoreSink writes. No GraphStore access of their own.
Details: docs/dev/spiders/orchestration/graph_sink/component_facts.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.interfaces import ComponentFacts
from generators.component_classifier import describe_options, format_option_choices


def option_labels_for(options_json: str) -> List[str]:
    """Clean, human-readable display strings for one `options` JSON blob -
    the same shape `component_tree.py`'s rendered `variants=[...]` line
    uses, computed once here so it can be stored alongside the raw JSON
    instead of only ever existing inside a generated .md file.
    Details: docs/dev/spiders/orchestration/graph_sink/component_facts.md#option_labels_for
    """
    return format_option_choices(describe_options(options_json))


def component_facts(comp: Dict[str, Any]) -> ComponentFacts:
    """Map one JS-discovered component dict's attribute/style facts onto `ComponentFacts`.
    `value` is deliberately left out: a fill's actual value is already captured by
    `record_component_interaction` at the moment it's set, which is the reliable source -
    re-reading a live `.value` here would just be a second, possibly-stale copy of the
    same fact (discovery can run before or after a fill).
    Details: docs/dev/spiders/orchestration/graph_sink/component_facts.md#component_facts
    """
    attributes = comp.get("attributes") or {}
    style = comp.get("style") or {}
    return ComponentFacts(
        css_class=attributes.get("class", ""),
        element_id=attributes.get("id", ""),
        href=attributes.get("href", ""),
        placeholder=comp.get("placeholder", ""),
        label=comp.get("label", ""),
        name=comp.get("name", ""),
        disabled=bool(comp.get("disabled", False)),
        required=bool(comp.get("required", False)),
        form=comp.get("form", ""),
        color=style.get("color", ""),
        background_color=style.get("background_color", ""),
        font_size=style.get("font_size", ""),
        font_weight=style.get("font_weight", ""),
        display=style.get("display", ""),
        position=style.get("position", ""),
    )
