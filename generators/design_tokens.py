"""D10: the palette and typographic scale a site actually uses, as DTCG
v2025.10 (docs/adr/0005).

The input to rebuilding the look. Not what the design *intended* - what
the rendered pages report - so an inconsistent legacy system produces
inconsistent tokens, and that inconsistency is itself the finding (the
usability audit reads the same data for its consistency rules).

**What is accurate here and what is deliberately missing.** Colours and font
sizes are computed CSS values, and interaction states are *declared* rules read
from the stylesheets - none of the three depend on viewport size or on whether
images loaded. Spacing is the one gap: it would have to come from element
geometry, which *is* viewport-dependent (the crawl measures at 800x600), so it
is absent rather than published as a number nobody should trust.

This document and `color_space.py` were deleted along with the measurement pass
and restored without it. The interaction states came back separately, once it
was clear that `extract_pseudo_styles.js` reads `document.styleSheets` and
therefore never needed that pass at all - it now runs in the ordinary discovery
pass. See `research/plan-segunda-ronda-de-documentos.md` B1 and nivel 2.

Details: docs/dev/generators/design_tokens.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .color_space import (
    JUST_NOTICEABLE_DIFFERENCE,
    parse_css_color,
    perceptual_distance,
    to_hex,
)
from .ledger import flat_component_ledger

_SCHEMA_PATH = "schemas/tokens.schema.json"
# ADR-0005's own stated threshold: three or more independent uses is what
# separates a real design token from an incidental, one-off style.
_SYSTEM_CANDIDATE_THRESHOLD = 3
# $extensions.pragma.source is reserved (docs/adr/0001's reserved-field
# pattern, applied here): CSS stylesheet URL, custom-property name, and
# matching-selector provenance need instrumentation this crawler doesn't
# have yet - discover_components.js resolves a computed style value per
# element, and extract_pseudo_styles.js matches selectors internally but
# never returns which one matched or which stylesheet it came from. A
# real value here later, not an invented one now.
_RESERVED_SOURCE = {"stylesheets": [], "css_variables": [], "selectors": [], "inline_style_count": 0}
# CSS properties extract_pseudo_styles.js tracks that DTCG's own "color"
# type already covers; everything else in TRACKED (box-shadow, outline,
# opacity) has no matching core DTCG type, so its own property name is
# used as $type instead - DTCG's type system is open-ended by design.
_COLOR_PROPERTIES = {"color", "background-color", "border-color"}

# Where each colour was found. Kept apart because a colour used for text
# and the same colour used as a surface are different tokens in any design
# system, even when the value matches.
TEXT = "text"
SURFACE = "surface"


@dataclass(frozen=True)
class ColorToken:
    """One colour the site uses, and how much.
    Details: docs/dev/generators/design_tokens.md#colortoken
    """

    name: str
    role: str
    value: str
    usage_count: int
    merged_from: Tuple[str, ...]


@dataclass(frozen=True)
class StateToken:
    """One value a control takes on `:hover` or `:focus`.
    Details: docs/dev/generators/design_tokens.md#statetoken
    """

    state: str
    property: str
    value: str
    usage_count: int


@dataclass(frozen=True)
class TypeToken:
    """One step of the type scale.
    Details: docs/dev/generators/design_tokens.md#typetoken
    """

    name: str
    font_size: str
    font_weight: str
    usage_count: int


def _cluster_colors(counts: Dict[Tuple[int, int, int], int]) -> List[Tuple[Tuple[int, int, int], int, List[str]]]:
    """Fold colours closer than one just-noticeable difference together.

    Greedy, most-used first: the winner of each cluster is the colour the
    site uses most, which is also the one a design system would keep. Not
    optimal clustering, and it does not need to be - the question is "is
    this the same grey", and the most-used member is the right
    representative for it either way.
    Details: docs/dev/generators/design_tokens.md#_cluster_colors
    """
    clusters: List[Tuple[Tuple[int, int, int], int, List[str]]] = []
    for rgb, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        for index, (leader, total, merged) in enumerate(clusters):
            if perceptual_distance(rgb, leader) <= JUST_NOTICEABLE_DIFFERENCE:
                clusters[index] = (leader, total + count, merged + [to_hex(rgb)])
                break
        else:
            clusters.append((rgb, count, []))
    return clusters


def _color_tokens(components: Sequence[Dict[str, Any]], field: str, role: str) -> List[ColorToken]:
    counts: Dict[Tuple[int, int, int], int] = {}
    for component in components:
        rgb = parse_css_color(component.get(field) or "")
        if rgb:
            counts[rgb] = counts.get(rgb, 0) + 1
    return [
        ColorToken(
            name=f"{role}-{index}",
            role=role,
            value=to_hex(rgb),
            usage_count=count,
            merged_from=tuple(sorted(merged)),
        )
        for index, (rgb, count, merged) in enumerate(_cluster_colors(counts), 1)
    ]


def build_color_tokens(components: Sequence[Dict[str, Any]]) -> List[ColorToken]:
    """Every colour the site renders, clustered and ranked by use.
    Details: docs/dev/generators/design_tokens.md#build_color_tokens
    """
    return _color_tokens(components, "color", TEXT) + _color_tokens(
        components, "background_color", SURFACE
    )


def _size_in_px(font_size: str) -> float:
    """Sort key for a CSS size; anything not in px sorts last rather than raising."""
    try:
        return float(font_size.replace("px", "").strip())
    except (AttributeError, ValueError):
        return -1.0


def build_type_tokens(components: Sequence[Dict[str, Any]]) -> List[TypeToken]:
    """Every distinct size/weight pair, largest first.

    The count per step is the useful part: six steps used evenly is a
    scale, twenty-three with most used once is drift, and the document
    lets a reader tell which they have.
    Details: docs/dev/generators/design_tokens.md#build_type_tokens
    """
    counts: Dict[Tuple[str, str], int] = {}
    for component in components:
        size, weight = component.get("font_size") or "", component.get("font_weight") or ""
        if not size:
            continue
        counts[(size, weight)] = counts.get((size, weight), 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-_size_in_px(item[0][0]), item[0][1]))
    return [
        TypeToken(name=f"type-{index}", font_size=size, font_weight=weight, usage_count=count)
        for index, ((size, weight), count) in enumerate(ordered, 1)
    ]


_NAMING_NOTE = (
    "Token names are positional (`text-1` is the most-used text colour), not semantic. The crawl "
    "sees that a colour is used, never what it means - naming one `brand-primary` would be a guess "
    "presented as a fact. Rename them when you adopt them."
)

def build_state_tokens(state_styles: Sequence[Dict[str, Any]]) -> List[StateToken]:
    """The `:hover`/`:focus` values the site declares, grouped by what they are.

    Read from `GraphStore.get_state_styles()` - the declared rules
    `extract_pseudo_styles.js` matched against real controls, not styles forced
    through a pseudo-state. A declared value *is* what a design token is:
    `#1a4f9c` as written beats the same colour resolved through whatever the
    element happened to inherit.

    Counted per `(state, property, value)`, so "eleven controls declare this
    hover colour" is the signal that separates a token from a one-off.

    A site serving its CSS cross-origin reports fewer of these than it has -
    `cssRules` throws for those stylesheets and there is no way around it, which
    is why the document says so rather than presenting `[]` as "declares no
    hover styles".
    Details: docs/dev/generators/design_tokens.md#build_state_tokens
    """
    counts: Dict[Tuple[str, str, str], int] = {}
    for entry in state_styles:
        key = (entry.get("state", ""), entry.get("property", ""), entry.get("value", ""))
        if all(key):
            counts[key] = counts.get(key, 0) + 1
    return [
        StateToken(state=state, property=css_property, value=value, usage_count=count)
        for (state, css_property, value), count in sorted(
            counts.items(), key=lambda item: (item[0][0], -item[1], item[0][1], item[0][2])
        )
    ]


_ABSENT_NOTE = (
    "**Spacing is absent.** It would come from element geometry, which the crawl measures at an "
    "800x600 viewport chosen for speed - a spacing scale derived from that describes a layout "
    "nobody sees. Everything else here is viewport-independent: colours and font sizes are computed "
    "CSS values, and the interaction states below are *declared* rules read from the stylesheets, "
    "so none of them depend on how wide the window was or on whether images loaded."
)

_STATE_CAVEAT = (
    "Declared `:hover` and `:focus` values, read from the site's own stylesheets. A site serving "
    "its CSS cross-origin reports fewer than it has - the browser refuses to expose those rules, "
    "and there is no way around it. Absent is not the same as \"this site declares no hover "
    "styles\"."
)


def _dtcg_token(dtcg_type: str, value: Any, usage_count: int) -> Dict[str, Any]:
    """One DTCG token: `$type`/`$value` plus pragma's own facts under
    `$extensions.pragma` - the DTCG spec's own vendor-extension mechanism,
    not a departure from it.
    Details: docs/dev/generators/design_tokens.md#_dtcg_token
    """
    return {
        "$type": dtcg_type,
        "$value": value,
        "$extensions": {
            "pragma": {
                "usage_frequency": {
                    "count": usage_count,
                    "is_system_candidate": usage_count >= _SYSTEM_CANDIDATE_THRESHOLD,
                },
                "source": dict(_RESERVED_SOURCE),
            }
        },
    }


def _state_dtcg_type(css_property: str) -> str:
    return "color" if css_property in _COLOR_PROPERTIES else css_property


def build_tokens_document(graph_store: Any) -> Dict[str, Any]:
    """The full `tokens.json` payload: DTCG's `core`/`semantic` split
    (docs/adr/0005). `semantic` stays empty in v1 - the crawl sees that a
    colour is used, never what it means (see `_NAMING_NOTE`), so aliasing
    a core token to a semantic name (`brand-primary`) would be a guess
    presented as fact.
    Details: docs/dev/generators/design_tokens.md#build_tokens_document
    """
    components = flat_component_ledger(graph_store)
    colors = build_color_tokens(components)
    types = build_type_tokens(components)
    states = build_state_tokens(graph_store.get_state_styles())

    core: Dict[str, Any] = {}
    if colors:
        core["color"] = {token.name: _dtcg_token("color", token.value, token.usage_count) for token in colors}
    if types:
        core["typography"] = {
            token.name: _dtcg_token(
                "typography", {"fontSize": token.font_size, "fontWeight": token.font_weight}, token.usage_count
            )
            for token in types
        }
    if states:
        core["interaction-state"] = {
            f"{token.state}-{token.property}-{index}": _dtcg_token(
                _state_dtcg_type(token.property), token.value, token.usage_count
            )
            for index, token in enumerate(states, 1)
        }
    return {"core": core, "semantic": {}}


def _is_system_candidate(token: Dict[str, Any]) -> bool:
    return token["$extensions"]["pragma"]["usage_frequency"]["is_system_candidate"]


def _usage_count(token: Dict[str, Any]) -> int:
    return token["$extensions"]["pragma"]["usage_frequency"]["count"]


def _swatch(value: str) -> str:
    """An inline colour chip - GitHub-Flavored Markdown renders raw HTML
    inside a table cell, and a hex code alone doesn't show what it looks
    like."""
    return f'<span style="display:inline-block;width:1em;height:1em;background:{value};border:1px solid #0003;vertical-align:middle;"></span> '


def _render_token_rows(entries: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    lines = ["| Token | Type | Value | Uses |", "|---|---|---|---|"]
    for name, token in entries:
        value = token["$value"]
        rendered_value = value if isinstance(value, str) else json.dumps(value)
        swatch = _swatch(value) if token["$type"] == "color" else ""
        lines.append(f"| `{name}` | {token['$type']} | {swatch}`{rendered_value}` | {_usage_count(token)} |")
    return lines


def _render_group(group_name: str, group: Dict[str, Dict[str, Any]]) -> List[str]:
    """One `core` group's swatch table, candidates first - ADR-0005's
    Source/View split: candidates (`is_system_candidate`) get the visible
    table, one-off styles are relegated to a collapsed appendix rather
    than diluting it.
    Details: docs/dev/generators/design_tokens.md#_render_group
    """
    candidates = sorted(
        ((name, token) for name, token in group.items() if _is_system_candidate(token)),
        key=lambda entry: -_usage_count(entry[1]),
    )
    one_offs = [(name, token) for name, token in group.items() if not _is_system_candidate(token)]

    lines = [f"## {group_name.replace('-', ' ').title()}", ""]
    if group_name == "interaction-state":
        lines += [_STATE_CAVEAT, ""]
    if candidates:
        lines += _render_token_rows(candidates) + [""]
    else:
        lines += [f"No token in this group was used {_SYSTEM_CANDIDATE_THRESHOLD}+ times this crawl.", ""]
    if one_offs:
        lines += [
            "<details><summary>One-off styles (used fewer times)</summary>", "",
            *_render_token_rows(one_offs), "",
            "</details>", "",
        ]
    return lines


def _render_tokens_view(document: Dict[str, Any], site: str) -> str:
    """`tokens.md` - mechanically rendered from `tokens.json`'s own `core`
    group, never hand-authored in parallel with it.

    `interaction-state` is always rendered, even with no tokens - its
    caveat (a cross-origin stylesheet reports fewer than the site
    declares) has to reach a reader whether or not any were captured, the
    same reason `_STATE_CAVEAT` existed before this document had a JSON
    source at all; an absent section would read as "no hover styles"
    rather than "pragma couldn't see them." `color`/`typography` carry no
    such caveat, so they're omitted entirely when empty instead.
    Details: docs/dev/generators/design_tokens.md#_render_tokens_view
    """
    lines = [f"# Design Tokens: {site}", "", _NAMING_NOTE, "", _ABSENT_NOTE, ""]
    core = document.get("core", {})
    if "color" in core:
        lines += _render_group("color", core["color"])
    if "typography" in core:
        lines += _render_group("typography", core["typography"])
    lines += _render_group("interaction-state", core.get("interaction-state", {}))
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("tokens")
class DesignTokensDocument(DocumentGenerator):
    """`tokens.json` (source, DTCG-validated) and `tokens.md` (view) -
    folds in the retired `tokens-data.json`, docs/adr/0005.
    Details: docs/dev/generators/design_tokens.md#designtokensdocument
    """

    name = "tokens"
    title = "Design Tokens"
    purpose = "The palette and type scale the site actually renders, ranked by use, as DTCG (docs/adr/0005)."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_tokens_document(request.graph_store)
        validate_against_schema(document, _SCHEMA_PATH)
        source = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        view = _render_tokens_view(document, request.site)
        return (
            DocumentOutput(filename="tokens", kind="source", extension="json", content=source),
            DocumentOutput(filename="tokens", kind="view", extension="md", content=view),
        )
