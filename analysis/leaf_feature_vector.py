"""Leaf-level component feature vector - issue #131's design
(`docs/dev/generators/leaf-feature-vector-design.md`), implemented here as
a pure value-producing function. Replaces `generators/component_family.py`'s
Jaccard-on-`css_class` clustering as the similarity signal two `Component`
records are compared by (cosine similarity over the vector this module
produces); storing the result into a real Kùzu `FLOAT[n]` column and
wiring the comparison into the pipeline is a later ticket's job (issue
#139) - this module has no I/O and does not know Kùzu exists.

`leaf_feature_vector` takes one component record - a plain dict shaped
like `DESCRIPTIVE_COMPONENT_FIELDS`/`ComponentFacts` (the same flat shape
`database/ladybug/component.py::get_component_ledger` already returns per
component, and the same shape `tests/test_component_family.py`'s
hand-authored dicts use), plus that page/site's `GeometryBuckets` (see
below) - and returns one `168`-dim `list[float]`, weighted per block per
`ComponentMatchingConfig.leaf_weights` and ready to concatenate into a
Kùzu vector column as-is.

`x`/`y` and `element_id` are excluded entirely, same reasoning as the
design doc: page-position and DOM-remount-unstable, not identity.
`text`/`label` are deliberately excluded too - kept for a separate,
cheaper text-proximity refinement pass (#128), not the indexed vector.

Details: docs/dev/analysis/leaf_feature_vector.md#module
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from generators.color_space import parse_css_color
from .component_matching_config import ComponentMatchingConfig, LeafWeights

# --- deterministic hashing ---

# hashlib.sha1, never Python's built-in hash() - process-randomized by
# PYTHONHASHSEED, not reproducible across runs. See the design doc's own
# "Why hashing" section for the tradeoff this buys (fixed dimensionality
# across every crawled site) against exact per-run vocabulary indexing.
def _bucket(value: str, bucket_count: int) -> int:
    digest = hashlib.sha1((value or "").encode()).digest()
    return int.from_bytes(digest[:4], "big") % bucket_count


def _hash_one_hot(value: str, bucket_count: int) -> List[float]:
    """One field's value, hashed into one of `bucket_count` slots - an
    empty string hashes like any other value, so "this component has no
    role" collides into one shared bucket rather than being dropped:
    lacking an attribute is itself a signal, not noise.
    Details: docs/dev/analysis/leaf_feature_vector.md#_hash_one_hot
    """
    vector = [0.0] * bucket_count
    vector[_bucket(value, bucket_count)] = 1.0
    return vector


def _hash_multi_hot(values: Iterable[str], bucket_count: int) -> List[float]:
    """`css_class`'s encoding - one hash per whitespace-split token,
    OR'd into a binary vector rather than one-hot per token, so a
    component's *set* of classes (independent of their order) is what
    determines this slice.
    Details: docs/dev/analysis/leaf_feature_vector.md#_hash_multi_hot
    """
    vector = [0.0] * bucket_count
    for value in values:
        if value:
            vector[_bucket(value, bucket_count)] = 1.0
    return vector


# --- closed-vocabulary one-hot (small, known value sets) ---

def _closed_one_hot(value: str, values: Sequence[str]) -> List[float]:
    vector = [0.0] * len(values)
    if value in values:
        vector[values.index(value)] = 1.0
    return vector


# The full closed set `generators/component_classifier.py::
# classify_component_type` can return, its templated `"text field
# (<input_type>)"` branch collapsed to the fixed `"text field"` (the
# specific `input_type` is already its own hashed field below) - single
# source of truth is that function's own branches, listed here rather
# than derived at runtime so this vocabulary (and therefore the vector's
# dimensionality) never shifts silently if that function grows a branch.
COMPONENT_TYPE_VALUES: Tuple[str, ...] = (
    "list/menu option", "combobox (searchable dropdown)", "checkbox",
    "radio button", "toggle switch", "tab", "native dropdown (select)",
    "text field", "submit button", "button", "link",
    "custom control (component-library element, no native tag/role)",
    "element",
)

POSITION_VALUES: Tuple[str, ...] = ("static", "relative", "absolute", "fixed", "sticky")

# --- bucket counts, per the design doc's layout table ---

_TAG_BUCKETS = 16
_ROLE_BUCKETS = 16
_INPUT_TYPE_BUCKETS = 12
_IDENTITY_STRING_BUCKETS = 16
_CSS_CLASS_BUCKETS = 32
_DISPLAY_BUCKETS = 10

_FONT_SIZE_SCALE = 32.0  # px, the design doc's normalization divisor
_FONT_WEIGHT_SCALE = 900.0


def _collapsed_component_type(value: str) -> str:
    if value.startswith("text field"):
        return "text field"
    return value


def _bool_dim(value: Any) -> float:
    return 1.0 if value else 0.0


def _parse_font_size(value: str) -> float:
    """`"16px"` -> `16.0`; anything unparseable (blank, a keyword like
    `"medium"` a stylesheet occasionally leaves uncomputed) -> `0.0`,
    the same "absence is a shared trait" default the hash blocks use.
    Details: docs/dev/analysis/leaf_feature_vector.md#_parse_font_size
    """
    text = (value or "").strip().removesuffix("px")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_font_weight(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _color_channels(value: str) -> Tuple[float, float, float]:
    rgb = parse_css_color(value or "")
    if rgb is None:
        return (0.0, 0.0, 0.0)
    r, g, b = rgb
    return (r / 255.0, g / 255.0, b / 255.0)


def _scale(vector: List[float], weight: float) -> List[float]:
    return [v * weight for v in vector]


# --- geometry: per-run tertile buckets, computed once over the whole set ---

@dataclass(frozen=True)
class GeometryBuckets:
    """Tertile edges for `width`/`height`, one pair per `(tag,
    component_type)` group, from `compute_geometry_buckets` - the one
    part of this design that needs the full component set in hand before
    any single vector can be computed.
    Details: docs/dev/analysis/leaf_feature_vector.md#geometrybuckets
    """

    width_edges: Dict[Tuple[str, str], Tuple[float, float]]
    height_edges: Dict[Tuple[str, str], Tuple[float, float]]


def _tertile_edges(values: List[float]) -> Tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    return (ordered[n // 3], ordered[(2 * n) // 3])


def compute_geometry_buckets(components: Sequence[Dict[str, Any]]) -> GeometryBuckets:
    """One tertile-edge pair per `(tag, component_type)` group, for both
    `width` and `height` - grouped so a component's size reads as
    small/medium/large relative to its own kind on this site, not against
    every component regardless of what it is. A group with fewer than 3
    members (not enough to split into thirds meaningfully) gets no edges
    at all; `_geometry_bucket_index` falls back to the middle bucket for
    any component whose group has none.
    Details: docs/dev/analysis/leaf_feature_vector.md#compute_geometry_buckets
    """
    widths: Dict[Tuple[str, str], List[float]] = {}
    heights: Dict[Tuple[str, str], List[float]] = {}
    for component in components:
        key = (component.get("tag", ""), component.get("component_type", ""))
        width, height = component.get("width"), component.get("height")
        if isinstance(width, (int, float)):
            widths.setdefault(key, []).append(float(width))
        if isinstance(height, (int, float)):
            heights.setdefault(key, []).append(float(height))
    return GeometryBuckets(
        width_edges={k: _tertile_edges(v) for k, v in widths.items() if len(v) >= 3},
        height_edges={k: _tertile_edges(v) for k, v in heights.items() if len(v) >= 3},
    )


def _geometry_bucket_index(value: Optional[float], edges: Optional[Tuple[float, float]]) -> int:
    if value is None or edges is None:
        return 1  # the middle bucket - no group-relative signal available
    low, high = edges
    if value <= low:
        return 0
    if value <= high:
        return 1
    return 2


def _geometry_one_hot(value: Optional[float], edges: Optional[Tuple[float, float]]) -> List[float]:
    vector = [0.0, 0.0, 0.0]
    vector[_geometry_bucket_index(value, edges)] = 1.0
    return vector


def leaf_feature_vector(
    component: Dict[str, Any],
    geometry_buckets: GeometryBuckets,
    config: Optional[ComponentMatchingConfig] = None,
) -> List[float]:
    """The 168-dim feature vector for one component record - concatenated
    blocks, each scaled by its `config.leaf_weights` entry before joining,
    so weight directly controls that block's share of the final cosine
    similarity. `config` defaults to `ComponentMatchingConfig()`'s
    hardcoded values when the caller has not loaded one.
    Details: docs/dev/analysis/leaf_feature_vector.md#leaf_feature_vector
    """
    weights: LeafWeights = (config or ComponentMatchingConfig()).leaf_weights
    tag = component.get("tag", "")
    role = component.get("role", "")
    input_type = component.get("input_type", "")
    component_type = _collapsed_component_type(component.get("component_type", ""))
    css_class = component.get("css_class", "")
    href = component.get("href", "")
    name = component.get("name", "")
    form = component.get("form", "")
    disabled = component.get("disabled", False)
    required = component.get("required", False)
    color = component.get("color", "")
    background_color = component.get("background_color", "")
    font_size = component.get("font_size", "")
    font_weight = component.get("font_weight", "")
    display = component.get("display", "")
    position = component.get("position", "")

    structural = (
        _hash_one_hot(tag, _TAG_BUCKETS)
        + _hash_one_hot(role, _ROLE_BUCKETS)
        + _hash_one_hot(input_type, _INPUT_TYPE_BUCKETS)
        + _closed_one_hot(component_type, COMPONENT_TYPE_VALUES)
        + [_bool_dim(disabled), _bool_dim(required), _bool_dim(form)]
    )

    identity_strings = (
        _hash_one_hot(href, _IDENTITY_STRING_BUCKETS)
        + _hash_one_hot(name, _IDENTITY_STRING_BUCKETS)
        + _hash_one_hot(form, _IDENTITY_STRING_BUCKETS)
    )

    css_class_tokens = _hash_multi_hot((css_class or "").split(), _CSS_CLASS_BUCKETS)

    color_r, color_g, color_b = _color_channels(color)
    bg_r, bg_g, bg_b = _color_channels(background_color)
    style = (
        [color_r, color_g, color_b, bg_r, bg_g, bg_b]
        + [_parse_font_size(font_size) / _FONT_SIZE_SCALE, _parse_font_weight(font_weight) / _FONT_WEIGHT_SCALE]
        + _hash_one_hot(display, _DISPLAY_BUCKETS)
        + _closed_one_hot(position, POSITION_VALUES)
    )

    geometry_key = (tag, component.get("component_type", ""))
    geometry = _geometry_one_hot(
        component.get("width"), geometry_buckets.width_edges.get(geometry_key)
    ) + _geometry_one_hot(
        component.get("height"), geometry_buckets.height_edges.get(geometry_key)
    )

    return (
        _scale(structural, weights.structural)
        + _scale(identity_strings, weights.identity_strings)
        + _scale(css_class_tokens, weights.css_class)
        + _scale(style, weights.style)
        + _scale(geometry, weights.geometry)
    )
