# analysis/tailwind_semantic_classes.py

## module

Parses a Tailwind `css_class` string into design concepts - color, spacing,
typography, border, shadow, layout - instead of the raw whitespace-split,
sha1-hashed tokens `leaf_feature_vector.py`'s `css_class` block used before
issue #168. Both `leaf_feature_vector.py` (`Component` leaves) and
`composite_matching.py` (`Container` roots) share this module, per the
downstream-consumer audit (#166) - converting one raw-hashing path and
leaving the other live would keep clustering partly on class-token noise
even after the vector nominally "went semantic."

Why this exists: two components can share every structural/style field and
differ only by one modifier class - `mapadeprofesionales.com`'s
doctor-listing cards, identical shells differing only by `border-extra-N`
(a per-doctor color badge). Under the old encoding that single token is one
coin-flip among 32 hash buckets, barely moving cosine similarity - two such
cards scored ~0.97, above even the leaf-exact threshold, risking a full
merge that would erase every doctor but one. Routing that token through a
dedicated `color` concept - a categorical "family" hash plus a literal
shade scalar - gives it enough weight to read as "the same family, a
different variant."

Tailwind-only, deliberately (this map's Out-of-scope: no other CSS
framework in scope until a non-Tailwind site shows up). Vocabulary covers
Tailwind's common utility surface, not its entire API; an unrecognized
token still contributes signal via `layout`'s catch-all hash rather than
being dropped - the same "absence/unknown is a shared trait" precedent
`leaf_feature_vector.py`'s hash blocks already follow.

## semantic_css_class_vector

The module's one entry point - `TOTAL_DIMS`-wide, concatenating six
concept blocks in `CONCEPTS`' order (color, spacing, typography, border,
shadow, layout). Every token is classified into exactly one concept -
state-variant prefixes (`hover:`, `md:`, ...) are stripped first, since
they modify *when* a utility applies, not *what* design property it
expresses.

## Color concept

`bg`/`ring`/`placeholder`/`fill`/`stroke`/`from`/`via`/`to`/`caret`/
`accent`/`outline`/`divide` read as "background" role; `text` and `border`
carry their own role. A numeric suffix on one of Tailwind's own default
palette names (`_KNOWN_COLOR_FAMILIES` - `blue`, `red`, `slate`, ...)
genuinely encodes a perceptual shade step, so it's split into a family hash
plus a `0.0`-`1.0` shade scalar (`_shade_scalar`, issue #169's calibration
starting point, not a precision claim). A theme/custom palette name (this
repo's own `extra` in `border-extra-N`) makes no such promise - Tailwind
lets a project map a custom scale to arbitrary, unrelated colors, so it's
kept as one opaque family value instead. `border-3`/`border-t`/`border-
dashed` are width/side/style utilities, not colors - `_is_border_structure_
value` disambiguates before a `border-`-prefixed token ever reaches the
color classifier. `bg-cover`/`bg-center`/... are background-position/size
utilities sharing `bg-`'s prefix, excluded via `_BG_LAYOUT_SUFFIXES`.

`_color_block` hashes each role's family tokens into its own
`_COLOR_FAMILY_BUCKETS`-wide slice, not one bucket set shared across all
three roles (issue #169's fix). Real markup showed why the shared version
broke: one shadcn/ui-style button's boilerplate alone carries 4-6 distinct
color tokens across background/text/border (state-variant `ring`/`outline`
utilities included), which saturated a single small shared bucket set to
all-`1.0` regardless of which specific palette value was present -
`border-extra-4` and `border-extra-1` produced byte-identical vectors.
Splitting by role (and widening each role's own bucket count to 16) gives
each role only its own tokens to distinguish, restoring separation.

## Spacing concept

Padding/margin/gap/space utilities - a small hash of which spacing
properties are present, plus one averaged, normalized numeric scale
scalar.

## Typography concept

Text size (`_TEXT_SIZE_ORDER`, an ordinal `0.0`-`1.0` scalar), font weight
(`_FONT_WEIGHT_NAMES`, its own ordinal scalar), font family, decoration/
case keywords - a property hash plus the two ordinals.

## Border concept

Width (numeric suffix, `/8.0`), radius (`rounded*`, `_RADIUS_ORDER`
ordinal), side/style keywords - a property hash plus a width scalar and a
radius ordinal scalar.

## Shadow concept

`shadow`/`shadow-*` - a small hash of the shadow's name (`md`, `soft`,
`2xl`, ...) plus a presence bool.

## Layout concept

Display, position, sizing (`w-`/`h-`), flex/grid alignment, overflow,
z-index, interaction/animation utilities (`cursor-`, `transition`,
`opacity-`, ...) - and the catch-all for any token matching none of the
above, so nothing is silently dropped.
