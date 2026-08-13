# `src/generators/accessibility.py`

## module

D11: WCAG 2.1 A/AA violations, from axe-core.

Separate from the usability audit because it has a named standard,
numbered criteria and a different reader. A developer fixing `4.1.2` and a
designer weighing "is this confusing" are not looking at the same
document.

**Why an engine and not our own rules.** The earlier plan had seven
hand-written rules here. The contrast check alone has to resolve stacked
backgrounds, opacity and gradients - and the first attempt at it read
`background_color` off the element itself, which is `rgba(0,0,0,0)` for
almost every element because the colour comes from an ancestor. It would
have produced wrong results at scale, silently. axe has ~90 rules
maintained by the people who define this space.

## accessibilityfinding

`element_count` is axe's own total, not the length of `resolved_paths`.
The per-rule node list is capped before storage (a global defect can hit
hundreds of elements) and reporting the cap as the count would understate
exactly the defects that matter most.

`unresolved` counts elements axe reported that did not map to one of this
project's own paths - most often inside a frame, or removed between the
audit and the resolution. They are counted rather than dropped: the
finding is real either way, it just cannot be pointed at a component node.

## build_axe_findings

Ordered by impact, then by how many elements a rule hits. Impact is axe's
own classification, which is the right authority for it.

## target_size

The one rule kept as ours. axe's `target-size` is not in its stable rule
set, and the geometry needed to check it is already on every component
node.

Skips components with no recorded width or height rather than treating
them as zero: a missing measurement is not a small one. Also skips the
`pointer` discovery layer - that is a catch-all net for markup with no
semantic tag or role, not a list of real controls, and flagging its
members would bury the genuine findings.

Note this rule reports at 24px (WCAG 2.2 AA minimum), not the 44px often
quoted, which is Apple's guideline rather than the standard.

## AccessibilityDocument

Two things the document is careful to say.

**An unrun measurement pass is not a clean result.** With no audit stored,
the obvious output is an empty document, which reads as "no accessibility
problems". It says instead that no page was audited and why.

**A clean report is not a compliant application.** Automated testing finds
on the order of a third of real WCAG problems. Everything reported is a
genuine violation - axe only reports what it can determine without
judgement - but keyboard operation, focus order and visible focus are
absent entirely, since they need the page driven by keyboard.

`(document)` in the failing-element list marks a rule about the page
itself rather than an element on it. `gp()` deliberately builds every path
starting below `<html>`, so a document-level rule like `html-has-lang`
resolves to nothing - and "nothing" would read as "we could not find it".
Found by running axe against a real page, where `html-has-lang` was the
only violation and came back unresolved.


## keyboard_findings

Three rules from the Tab walk, none of them reachable by reading the DOM.

- **`focus-visible` (2.4.7).** The common real failure is a reset
  stylesheet removing the UA outline and never putting anything back. A UA
  default counts as visible; `outline: none` with no replacement does not.
- **`focus-order` (2.4.3).** A stop whose DOM position goes *backwards*
  relative to the previous one means Tab jumped against reading order -
  usually a positive `tabindex`.
- **`focus-offscreen`.** Focus landing on something with no size on screen
  leaves a keyboard user with nothing to see and no idea where they are.

The coverage note changed with these: keyboard operation, focus order and
visible focus used to be listed as entirely absent. What remains absent is
the judgement-dependent part - whether a label is clear, whether an order
is logical to a person - which is not automatable at all.
