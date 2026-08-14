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


## StateToken

## build_state_tokens

The `:hover`/`:focus` values a site declares, which is what separates a
token file of colours and typography from a component specification
someone can actually build against. A catalogue without interaction states
is incomplete for Storybook, and the component catalogue said so before
these existed.

Read from the stylesheets during the measurement pass - see
`page_extraction.extract_pseudo_styles` for why declared rather than
computed, and for the cross-origin limit that makes the result a lower
bound.

The empty case says *why* it is empty. "No hover styles were read" and
"this site declares no hover styles" are different facts, and only one of
them is a finding about the site.
