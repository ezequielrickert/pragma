# `generators/design_tokens.py`

## module

D10: the palette and type scale the site actually renders.

Not what the design *intended* - what the pages report. An inconsistent
legacy system therefore produces inconsistent tokens, and that is the
correct output: the inconsistency is itself a finding, which the usability
audit reports from the same data.

**What is trustworthy here and what is missing.** Colours and font sizes
are computed CSS values: they do not depend on the viewport, and blocked
images do not affect `background-color` (only `background-image`, which is
not read). So the palette and the type scale are real despite the crawl's
speed-tuned browser. Spacing is the opposite case - it would come from
element geometry measured at 800x600 - and is absent rather than published
as a number nobody should trust.

## ColorToken

`role` separates a colour used for text from the same colour used as a
surface. They are different tokens in any design system even when the
value matches, and merging them would lose the distinction the reader
needs most.

`merged_from` lists what was folded in, so a reader can see the palette
was cleaned rather than guess whether a colour is missing.

## TypeToken

## _cluster_colors

Greedy, most-used first. The winner of each cluster is the colour the site
uses most, which is also the one a design system would keep.

Not optimal clustering, and it does not need to be: the question is "is
this the same grey", every candidate is within one just-noticeable
difference of the leader, and any member would round-trip to the same
design decision.

## build_color_tokens

## build_type_tokens

The per-step count is the useful part. Six steps used evenly is a scale;
twenty-three steps with most used once is drift. The document reports
counts so a reader can tell which they have rather than being told.

## DesignTokensDocument

Two notes appear before any table, both load-bearing:

- **Names are positional.** `text-1` is the most-used text colour, not the
  brand primary. The crawl sees that a colour is used, never what it
  means; naming one `brand-primary` would be a guess presented as a fact,
  and someone would build on it.
- **Spacing is absent, and why.** A reader has to be able to tell "nobody
  implemented this" from "this cannot be measured honestly yet".

## DesignTokensData

The same tokens as JSON for a Tailwind or design-system config, sharing
the builders with the Markdown document so the two cannot disagree. The
spacing note is carried as structured data (`{"absent": true, "reason":
...}`) rather than dropped, so a generator consuming the JSON does not
silently emit a config with no spacing scale and no explanation.


## absence

`_ABSENT_NOTE` covers spacing and interaction states together because they
share one cause: both need the measurement pass, and this pipeline does not
have one. Stating them together stops a reader concluding that the palette is
equally provisional - it is not, and the note says why.

The JSON document carries the same fact as data (`absent: {spacing, state,
reason}`) so a Tailwind or Storybook generator consuming it can tell a token
set that is complete from one that is missing a dimension, without parsing
prose.

**Restored, not rewritten.** This generator and `color_space.py` were deleted
with the measurement pass and brought back from history minus
`build_state_tokens` and its two `get_page_measurements` calls. That was the
whole of their dependency on it. See
`research/plan-segunda-ronda-de-documentos.md` B1.

## statetoken

One value a control takes on `:hover` or `:focus`, with how many controls
declare it.

The count is what separates a token from a one-off: eleven controls sharing a
hover colour is a design decision, one control having its own is an exception.

## build_state_tokens

Counts `get_state_styles()` per `(state, property, value)`.

Reads **declared** rules, not styles forced through a pseudo-state, and that is
the right input rather than a limitation: a declared value *is* what a design
token is. `#1a4f9c` as written in the stylesheet beats the same colour resolved
through whatever the element happened to inherit.

A row missing any of state, property or value is dropped - a declaration with no
value is not a token.

This came back separately from the rest of the document. It was deleted with the
measurement pass on the assumption that it needed one; it does not, because
`extract_pseudo_styles.js` only reads stylesheets. See
`research/plan-segunda-ronda-de-documentos.md` nivel 2.
