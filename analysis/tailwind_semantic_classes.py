"""Parses a Tailwind `css_class` string into design *concepts* - color,
spacing, typography, border, shadow, layout - instead of the raw
whitespace-split, sha1-hashed tokens `leaf_feature_vector.py`'s `css_class`
block used before issue #168. Both `leaf_feature_vector.py` (`Component`
leaves) and `composite_matching.py` (`Container` roots) share this module,
per the downstream-consumer audit (#166): converting one raw-hashing path
and leaving the other live would keep clustering partly on class-token
noise even after the vector nominally "went semantic."

Why this exists: two components can share every structural/style field and
differ only by one modifier class - e.g. `mapadeprofesionales.com`'s
doctor-listing cards, identical shells differing only by `border-extra-N`,
a per-doctor color badge. Under the old encoding that single token is one
coin-flip among 32 hash buckets, barely moving cosine similarity (an empty
`Component.text` diff aside, two such cards scored ~0.97 - above even the
leaf-exact threshold, risking a full merge that would erase every doctor
but one). Routing that token through a dedicated `color` concept - a small
categorical "family" hash plus a literal, unhashed shade scalar - gives it
enough weight to read as "the same family, a different variant" instead of
"noise that barely counts."

Tailwind-only, deliberately (this map's Out-of-scope: no other CSS
framework in scope until a non-Tailwind site actually shows up). Vocabulary
below covers Tailwind's common utility surface, not its entire API surface;
an unrecognized token still contributes signal rather than being dropped -
it falls into `layout`'s catch-all hash, the same "absence/unknown is a
shared trait, not noise" precedent `leaf_feature_vector.py`'s hash blocks
already follow.

Details: docs/dev/analysis/tailwind_semantic_classes.md#module
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .deterministic_hashing import hash_multi_hot as _hash_multi_hot

CONCEPTS: Tuple[str, ...] = ("color", "spacing", "typography", "border", "shadow", "layout")

# --- concept vocabulary ---

# Property prefixes Tailwind actually uses for color, keyed to the role a
# shade scalar is tracked under below. `bg`/`ring`/`placeholder`/`fill`/
# `stroke`/`from`/`via`/`to`/`caret`/`accent`/`outline`/`divide` all read
# as "background-ish" for the scalar's purposes - only `text` and `border`
# carry their own dedicated scalar, since those are the two roles that
# distinguish the doctor-card pattern this module exists for.
_COLOR_PREFIX_ROLE: Dict[str, str] = {
    "bg": "background", "ring": "background", "placeholder": "background",
    "fill": "background", "stroke": "background", "from": "background",
    "via": "background", "to": "background", "caret": "background",
    "accent": "background", "outline": "background", "divide": "background",
    "text": "text", "border": "border",
}

# Tailwind's own default palette (v3) - a numeric suffix on one of these
# genuinely encodes a perceptual shade step, so `blue-500` and `blue-600`
# read as "same family, one step darker." A theme/custom palette name (this
# repo's own `extra` in `border-extra-N`) makes no such promise - Tailwind
# lets a project map `extra-1`..`extra-N` to arbitrary, unrelated colors,
# so splitting it the same way would claim a shade relationship that isn't
# there. Anything not in this set is kept as one opaque family value
# instead (the full `extra-6` token, not `extra` + a shade scalar).
_KNOWN_COLOR_FAMILIES = frozenset({
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow",
    "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet",
    "purple", "fuchsia", "pink", "rose",
})

# `bg-`'s non-color utilities (background-position/size/repeat/attachment)
# - these share `bg-`'s prefix but are layout concerns, not color.
_BG_LAYOUT_SUFFIXES = frozenset({
    "cover", "contain", "fixed", "local", "scroll", "repeat", "no-repeat",
    "repeat-x", "repeat-y", "center", "top", "bottom", "left", "right",
    "auto", "none",
})

_TEXT_SIZE_ORDER = ("xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl")
_FONT_WEIGHT_NAMES = frozenset({
    "thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black",
})
_BORDER_STYLE_NAMES = frozenset({"solid", "dashed", "dotted", "double", "none", "hidden"})
_BORDER_SIDES = frozenset({"t", "r", "b", "l", "x", "y"})
_RADIUS_ORDER = ("none", "sm", "", "md", "lg", "xl", "2xl", "3xl", "full")

_TYPOGRAPHY_KEYWORDS = frozenset({
    "italic", "not-italic", "underline", "overline", "line-through", "no-underline",
    "uppercase", "lowercase", "capitalize", "normal-case", "antialiased",
})
_LAYOUT_PREFIXES = (
    "flex", "grid", "block", "inline", "hidden", "table", "w-", "h-", "min-w-", "max-w-",
    "min-h-", "max-h-", "justify-", "items-", "content-", "self-", "place-", "absolute",
    "relative", "fixed", "sticky", "static", "top-", "right-", "bottom-", "left-", "inset-",
    "z-", "overflow-", "col-", "row-", "order-", "float-", "clear-", "object-", "aspect-",
    "cursor-", "select-", "pointer-events-", "visible", "invisible", "opacity-", "transition",
    "duration-", "ease-", "delay-", "animate-", "transform", "scale-", "rotate-", "translate-",
    "skew-", "origin-",
)


def _strip_variant_prefix(token: str) -> str:
    """`"hover:shadow-2xl"` -> `"shadow-2xl"` - a state-conditional utility
    (`hover:`/`focus:`/`md:`/`dark:`/...) still expresses the same base
    concept, just applied conditionally; the condition itself carries no
    design-property information this parser tracks.
    """
    return token.rsplit(":", 1)[-1]


def _split_value(token: str, prefix: str) -> str:
    return token[len(prefix) + 1:]


def _shade_scalar(value: str) -> float:
    """A palette shade normalized to roughly `0.0`-`1.0` - standard
    Tailwind palettes step 50..950, a custom/theme scale (this repo's own
    `border-extra-1`..`border-extra-8`) steps in small integers. Both are
    heuristically distinguished by magnitude; the exact mapping is a
    starting point for issue #169's calibration pass, not a claim of
    precision.
    """
    if not value.isdigit():
        return 0.0
    number = float(value)
    return number / 1000.0 if number >= 50 else number / 10.0


@dataclass(frozen=True)
class _ColorToken:
    role: str  # "background" | "text" | "border"
    family: str  # e.g. "white", "extra" (from border-extra-6), "blue" (from text-blue-500)
    shade: float


def _classify_color(prefix: str, token: str) -> Optional[_ColorToken]:
    role = _COLOR_PREFIX_ROLE.get(prefix)
    if role is None:
        return None
    value = _split_value(token, prefix)
    if prefix == "bg" and value in _BG_LAYOUT_SUFFIXES:
        return None
    if prefix in ("border", "divide") and _is_border_structure_value(value):
        return None  # width/side/style utility (e.g. border-3, border-t) - not a color
    parts = value.split("-")
    base = "-".join(parts[:-1])
    if len(parts) > 1 and parts[-1].isdigit() and base in _KNOWN_COLOR_FAMILIES:
        family, shade = base, _shade_scalar(parts[-1])
    else:
        family, shade = value, 0.0  # opaque - custom palette name, or shade-less (white/black/...)
    return _ColorToken(role=role, family=f"{prefix}:{family}", shade=shade)


def _is_typography(token: str) -> bool:
    if token in _TYPOGRAPHY_KEYWORDS:
        return True
    if token.startswith(("leading-", "tracking-")):
        return True
    if token.startswith("font-"):
        value = _split_value(token, "font")
        return value in _FONT_WEIGHT_NAMES or not value.isdigit()
    if token.startswith("text-"):
        return _split_value(token, "text") in _TEXT_SIZE_ORDER
    return False


def _is_spacing(token: str) -> bool:
    if re.match(r"^-?(p|m)([trblxy])?-", token):
        return True
    return bool(re.match(r"^(gap|space-[xy])(-[xy])?-", token))


def _is_shadow(token: str) -> bool:
    return token == "shadow" or token.startswith("shadow-")


def _is_border_structure_value(value: str) -> bool:
    """`value` is whatever follows `border-`/`divide-` - `True` for a
    width/side/style utility (`3`, `t`, `t-2`, `dashed`), `False` for
    anything that reads as a color instead (`extra-6`, `red-500`, `white`).
    An optional leading side letter (`t`/`r`/`b`/`l`/`x`/`y`) is stripped
    first, since `border-t-2` is still a width utility, not a color.
    """
    parts = value.split("-")
    if parts and parts[0] in _BORDER_SIDES:
        parts = parts[1:]
    if not parts or parts == [""]:
        return True  # bare "border-t" - a side with the default width
    return parts[0] in _BORDER_STYLE_NAMES or all(p.isdigit() for p in parts)


def _is_border(token: str) -> bool:
    if token == "border" or token.startswith("rounded"):
        return True
    if not token.startswith("border-") and not token.startswith("divide-"):
        return False
    return _is_border_structure_value(token.split("-", 1)[1])


def _is_layout(token: str) -> bool:
    return token.startswith(_LAYOUT_PREFIXES)


# --- per-concept vector builders ---

_COLOR_FAMILY_BUCKETS = 16  # per role - see _color_block
_SPACING_PROPERTY_BUCKETS = 8
_TYPOGRAPHY_PROPERTY_BUCKETS = 6
_BORDER_PROPERTY_BUCKETS = 6
_SHADOW_NAME_BUCKETS = 4
_LAYOUT_BUCKETS = 12

_COLOR_ROLES: Tuple[str, ...] = ("background", "text", "border")

COLOR_DIMS = _COLOR_FAMILY_BUCKETS * len(_COLOR_ROLES) + 3  # + one shade scalar per role
SPACING_DIMS = _SPACING_PROPERTY_BUCKETS + 1  # + average scale scalar
TYPOGRAPHY_DIMS = _TYPOGRAPHY_PROPERTY_BUCKETS + 2  # + size ordinal + weight ordinal
BORDER_DIMS = _BORDER_PROPERTY_BUCKETS + 2  # + width scalar + radius ordinal
SHADOW_DIMS = _SHADOW_NAME_BUCKETS + 1  # + presence bool
LAYOUT_DIMS = _LAYOUT_BUCKETS

TOTAL_DIMS = COLOR_DIMS + SPACING_DIMS + TYPOGRAPHY_DIMS + BORDER_DIMS + SHADOW_DIMS + LAYOUT_DIMS


def _color_block(color_tokens: List[_ColorToken]) -> List[float]:
    """One `_COLOR_FAMILY_BUCKETS`-wide multi-hot per role, not one shared
    across all three (issue #169's finding): a single button's boilerplate
    alone routinely carries 4-6 distinct color tokens across background/
    text/border (state-variant ring/outline utilities included) - sharing
    one small bucket set across all of them saturated it to all-1.0 on
    real markup, erasing the one token (`border-extra-N`) actually meant
    to distinguish two components. Splitting by role keeps each role's
    bucket set sized to what that role alone needs to distinguish.
    """
    families_by_role: Dict[str, List[str]] = {role: [] for role in _COLOR_ROLES}
    shade_by_role = {role: 0.0 for role in _COLOR_ROLES}
    for token in color_tokens:
        families_by_role[token.role].append(token.family)
        shade_by_role[token.role] = max(shade_by_role[token.role], token.shade)
    families = [
        value
        for role in _COLOR_ROLES
        for value in _hash_multi_hot(families_by_role[role], _COLOR_FAMILY_BUCKETS)
    ]
    return families + [shade_by_role[role] for role in _COLOR_ROLES]


def _spacing_block(tokens: List[str]) -> List[float]:
    properties = [token.split("-")[0] for token in tokens]
    scales = [float(m.group(0)) for token in tokens for m in [re.search(r"[\d.]+$", token)] if m]
    average_scale = (sum(scales) / len(scales) / 16.0) if scales else 0.0
    return _hash_multi_hot(properties, _SPACING_PROPERTY_BUCKETS) + [average_scale]


def _typography_block(tokens: List[str]) -> List[float]:
    properties, size_ordinal, weight_ordinal = [], 0.0, 0.0
    for token in tokens:
        if token.startswith("text-"):
            properties.append("size")
            value = _split_value(token, "text")
            if value in _TEXT_SIZE_ORDER:
                size_ordinal = _TEXT_SIZE_ORDER.index(value) / (len(_TEXT_SIZE_ORDER) - 1)
        elif token.startswith("font-"):
            value = _split_value(token, "font")
            if value in _FONT_WEIGHT_NAMES:
                properties.append("weight")
                weight_ordinal = sorted(_FONT_WEIGHT_NAMES).index(value) / (len(_FONT_WEIGHT_NAMES) - 1)
            else:
                properties.append("family")
        else:
            properties.append(token.split("-")[0])
    return _hash_multi_hot(properties, _TYPOGRAPHY_PROPERTY_BUCKETS) + [size_ordinal, weight_ordinal]


def _border_block(tokens: List[str]) -> List[float]:
    properties, width_scalar, radius_ordinal = [], 0.0, 0.0
    for token in tokens:
        if token.startswith("rounded"):
            value = token[len("rounded"):].lstrip("-")
            properties.append("radius")
            if value in _RADIUS_ORDER:
                radius_ordinal = _RADIUS_ORDER.index(value) / (len(_RADIUS_ORDER) - 1)
        else:
            properties.append("width")
            match = re.search(r"(\d+)$", token)
            if match:
                width_scalar = max(width_scalar, float(match.group(1)) / 8.0)
            elif token == "border":
                width_scalar = max(width_scalar, 1.0 / 8.0)
    return _hash_multi_hot(properties, _BORDER_PROPERTY_BUCKETS) + [width_scalar, radius_ordinal]


def _shadow_block(tokens: List[str]) -> List[float]:
    names = [token[len("shadow"):].lstrip("-") or "DEFAULT" for token in tokens]
    presence = 1.0 if tokens else 0.0
    return _hash_multi_hot(names, _SHADOW_NAME_BUCKETS) + [presence]


def _layout_block(tokens: List[str]) -> List[float]:
    return _hash_multi_hot(tokens, _LAYOUT_BUCKETS)


def semantic_css_class_vector(css_class: str) -> List[float]:
    """`css_class`'s replacement for `leaf_feature_vector.py`'s old raw
    `_hash_multi_hot` block: one design-concept vector, `TOTAL_DIMS` wide,
    concatenated in `CONCEPTS`' order (color, spacing, typography, border,
    shadow, layout). Every token is classified into exactly one concept -
    state-variant prefixes (`hover:`, `md:`, ...) are stripped first,
    since they modify *when* a utility applies, not *what* design property
    it expresses. A token matching no known Tailwind vocabulary still
    contributes: it falls into `layout`'s catch-all hash rather than being
    silently dropped.
    Details: docs/dev/analysis/tailwind_semantic_classes.md#semantic_css_class_vector
    """
    color_tokens: List[_ColorToken] = []
    spacing, typography, border, shadow, layout = [], [], [], [], []

    for raw in (css_class or "").split():
        token = _strip_variant_prefix(raw)
        if not token:
            continue
        prefix = token.split("-", 1)[0]
        color = _classify_color(prefix, token) if prefix in _COLOR_PREFIX_ROLE else None
        if color is not None:
            color_tokens.append(color)
        elif _is_typography(token):
            typography.append(token)
        elif _is_spacing(token):
            spacing.append(token)
        elif _is_shadow(token):
            shadow.append(token)
        elif _is_border(token):
            border.append(token)
        elif _is_layout(token):
            layout.append(token)
        else:
            layout.append(token)  # unrecognized - still a signal, not noise

    return (
        _color_block(color_tokens)
        + _spacing_block(spacing)
        + _typography_block(typography)
        + _border_block(border)
        + _shadow_block(shadow)
        + _layout_block(layout)
    )
