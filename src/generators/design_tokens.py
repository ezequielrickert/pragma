"""D10: the palette and typographic scale a site actually uses.

The input to rebuilding the look. Not what the design *intended* - what
the rendered pages report - so an inconsistent legacy system produces
inconsistent tokens, and that inconsistency is itself the finding (the
usability audit reads the same data for its consistency rules).

**What is accurate today and what is not.** Colours and font sizes are
computed CSS values, independent of viewport size and of the crawl's
blocked images, so the palette and the type scale are real. Spacing would
have to come from element geometry, which *is* viewport-dependent - the
crawl measures at 800x600 - so it is deliberately absent until the
measurement pass exists, rather than published as a number nobody should
trust.

Details: docs/dev/generators/design_tokens.md#module
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence, Tuple

from ..core.documents import DocumentGenerator, DocumentRequest
from ..core.registry import DOCUMENT_REGISTRY
from .color_space import (
    JUST_NOTICEABLE_DIFFERENCE,
    parse_css_color,
    perceptual_distance,
    to_hex,
)
from .ledger import flat_component_ledger

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

def build_state_tokens(measurements: Dict[str, Dict[str, Any]]) -> List["StateToken"]:
    """The `:hover`/`:focus` values a site declares, grouped by what they are.

    Read from the stylesheets rather than from a forced pseudo-state,
    because a declared value *is* what a token is - `#1a4f9c` as written
    beats the same colour resolved through whatever an element inherited.

    A site serving its CSS cross-origin reports fewer of these than it has:
    `cssRules` throws for those stylesheets and there is no way around it.
    Details: docs/dev/generators/design_tokens.md#build_state_tokens
    """
    counts: Dict[Tuple[str, str, str], int] = {}
    for page in measurements.values():
        for entry in page.get("pseudo_styles") or []:
            for state, declarations in (entry.get("states") or {}).items():
                for prop, value in declarations.items():
                    if value:
                        counts[(state, prop, value)] = counts.get((state, prop, value), 0) + 1
    return [
        StateToken(state=state, property=prop, value=value, usage_count=count)
        for (state, prop, value), count in sorted(counts.items(), key=lambda item: (item[0][0], -item[1]))
    ]


_SPACING_NOTE = (
    "Spacing tokens are absent. They would come from element geometry, which the crawl measures at "
    "an 800x600 viewport chosen for speed - a spacing scale derived from that describes a layout "
    "nobody sees. Colours and font sizes are computed CSS values and do not have this problem."
)


@DOCUMENT_REGISTRY.register("tokens")
class DesignTokensDocument(DocumentGenerator):
    """Details: docs/dev/generators/design_tokens.md#designtokensdocument"""

    name = "tokens"
    title = "Design Tokens"
    purpose = "The palette and type scale the site actually renders, ranked by use."

    def generate(self, request: DocumentRequest) -> str:
        components = flat_component_ledger(request.graph_store, request.site)
        colors = build_color_tokens(components)
        types = build_type_tokens(components)

        lines = [f"# Design Tokens: {request.site}", "", _NAMING_NOTE, "", _SPACING_NOTE, ""]
        if not colors and not types:
            lines.append("No computed styles were recorded for this crawl.")
            return "\n".join(lines) + "\n"

        if colors:
            lines += ["## Colour", "", "| Token | Role | Value | Uses | Merged near-identical |",
                      "|---|---|---|---|---|"]
            lines += [
                f"| `{c.name}` | {c.role} | `{c.value}` | {c.usage_count} | "
                f"{', '.join(c.merged_from) if c.merged_from else '-'} |"
                for c in colors
            ]
            lines.append("")
        if types:
            lines += ["## Type scale", "", "| Token | Size | Weight | Uses |", "|---|---|---|---|"]
            lines += [f"| `{t.name}` | {t.font_size} | {t.font_weight} | {t.usage_count} |" for t in types]
            lines.append("")

        states = build_state_tokens(request.graph_store.get_page_measurements(request.site))
        if states:
            lines += [
                "## Interaction states",
                "",
                "Declared `:hover` and `:focus` values, read from the stylesheets during the "
                "measurement pass. A component catalogue without these is not usable in Storybook.",
                "",
                "| State | Property | Value | Uses |",
                "|---|---|---|---|",
            ]
            lines += [f"| {s.state} | `{s.property}` | `{s.value}` | {s.usage_count} |" for s in states]
        else:
            lines += [
                "## Interaction states",
                "",
                "None were read. Either the measurement pass has not run, or the site serves its CSS "
                "cross-origin - the browser refuses to expose those rules, and there is no way "
                "around it. Absent is not the same as 'this site declares no hover styles'.",
            ]
        lines.append("")
        return "\n".join(lines)


@DOCUMENT_REGISTRY.register("tokens-data")
class DesignTokensData(DocumentGenerator):
    """The same tokens as JSON, for a Tailwind or design-system config.
    Details: docs/dev/generators/design_tokens.md#designtokensdata
    """

    name = "tokens-data"
    title = "Design Tokens (data)"
    purpose = "The palette and type scale as structured JSON, for a Tailwind or design-system config."
    extension = "json"

    def generate(self, request: DocumentRequest) -> str:
        components = flat_component_ledger(request.graph_store, request.site)
        payload = {
            "site": request.site,
            "note": _NAMING_NOTE,
            "spacing": {"absent": True, "reason": _SPACING_NOTE},
            "color": [asdict(token) for token in build_color_tokens(components)],
            "type": [asdict(token) for token in build_type_tokens(components)],
            "state": [
                asdict(token)
                for token in build_state_tokens(request.graph_store.get_page_measurements(request.site))
            ],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
