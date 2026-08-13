# `src/generators/color_space.py`

## module

Enough colour science to group colours the way an eye does, and no more.

It exists for one decision. A real application's computed styles hold
dozens of near-identical greys, and a "palette" listing all of them is a
dump. Grouping needs a perceptual distance, and RGB distance is not one:
`#000000`/`#000010` and `#00FF00`/`#00FF10` sit the same RGB distance
apart and nowhere near the same visual distance.

## parse_css_color

`getComputedStyle` always reports `rgb()`/`rgba()`, whatever the
stylesheet said - no hex, no named colours - so that is the only form
parsed.

Returns `None` for a fully transparent colour as well as for an
unparseable one. `rgba(0, 0, 0, 0)` is what an element with no background
of its own reports, and it is by far the most common value in a real
crawl; reading it as "black" would put a black nobody can see at the top
of every palette.

## to_lab

sRGB through linear RGB and CIE XYZ (D65) to L\*a\*b\*, the space where
Euclidean distance approximates perceived difference. Verified at the two
fixed points a mistake would break: black is L\*=0, white is L\*=100.

## perceptual_distance

CIE76, not CIEDE2000, and that is a decision rather than an oversight.
CIEDE2000 is more faithful and substantially more code; this is used for
exactly one question - "are these two greys the same grey" - where CIE76's
known weakness, overstating differences among saturated blues, does not
arise. If the palette ever needs to rank colours by similarity rather than
merely cluster near-duplicates, revisit it.

## just_noticeable_difference

2.3 is the conventional CIE76 threshold below which two colours are
indistinguishable to a normal observer. Using the perceptual threshold
rather than a tuned constant means the number has a meaning someone can
check, instead of being whatever produced a nice-looking palette on one
site.
