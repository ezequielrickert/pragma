"""Enough colour science to tell two colours apart the way an eye does.

Exists for one job: a real application's computed styles contain dozens of
near-identical greys, and a palette that lists all of them is a dump, not a
palette. Grouping needs a perceptual distance, and RGB distance is not one
- `#000000`/`#000010` and `#00FF00`/`#00FF10` are the same RGB distance
apart and nowhere near the same visual distance.

Details: docs/dev/generators/color_space.md#module
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# CSS colours as getComputedStyle reports them: always rgb()/rgba(), never
# a hex literal or a named colour, whatever the stylesheet said.
_RGB_PATTERN = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+))?\s*\)")

# D65 white point, the illuminant sRGB is defined against.
_WHITE_POINT = (95.047, 100.0, 108.883)

# Below this, two colours are the same colour for design purposes: 2.3 is
# the conventional "just noticeable difference" in CIE76.
# Details: docs/dev/generators/color_space.md#just_noticeable_difference
JUST_NOTICEABLE_DIFFERENCE = 2.3


def parse_css_color(value: str) -> Optional[Tuple[int, int, int]]:
    """`(r, g, b)` from a computed CSS colour, or `None`.

    `None` for a fully transparent colour as well as for an unparseable
    one: `rgba(0, 0, 0, 0)` is what an element with no background of its
    own reports, and treating that as "black" would put a black that
    nobody can see at the top of every palette.
    Details: docs/dev/generators/color_space.md#parse_css_color
    """
    match = _RGB_PATTERN.search(value or "")
    if not match:
        return None
    if match.group(4) is not None and float(match.group(4)) == 0:
        return None
    return tuple(int(round(float(match.group(i)))) for i in (1, 2, 3))  # type: ignore[return-value]


def _to_linear(channel: int) -> float:
    ratio = channel / 255
    return ratio / 12.92 if ratio <= 0.04045 else ((ratio + 0.055) / 1.055) ** 2.4


def _pivot(ratio: float) -> float:
    return ratio ** (1 / 3) if ratio > 0.008856 else (7.787 * ratio) + (16 / 116)


def to_lab(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """sRGB to CIE L*a*b*, the space where distance tracks perception.
    Details: docs/dev/generators/color_space.md#to_lab
    """
    red, green, blue = (_to_linear(channel) * 100 for channel in rgb)
    x = red * 0.4124 + green * 0.3576 + blue * 0.1805
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = red * 0.0193 + green * 0.1192 + blue * 0.9505
    fx, fy, fz = (_pivot(value / white) for value, white in zip((x, y, z), _WHITE_POINT))
    return (116 * fy) - 16, 500 * (fx - fy), 200 * (fy - fz)


def perceptual_distance(first: Tuple[int, int, int], second: Tuple[int, int, int]) -> float:
    """CIE76 delta-E between two sRGB colours.

    CIE76 and not CIEDE2000, deliberately: CIEDE2000 is more faithful,
    substantially more code, and this is used for one decision - "are
    these two greys the same grey" - where CIE76's known weakness (it
    overstates differences in saturated blues) does not apply.
    Details: docs/dev/generators/color_space.md#perceptual_distance
    """
    return sum((a - b) ** 2 for a, b in zip(to_lab(first), to_lab(second))) ** 0.5


def to_hex(rgb: Tuple[int, int, int]) -> str:
    """`(45, 119, 55)` -> `"#2d7737"` - what a design tool expects."""
    return "#" + "".join(f"{channel:02x}" for channel in rgb)
