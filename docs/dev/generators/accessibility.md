# generators/accessibility.py

## module

D11, rebuilt without a live axe-core run.

The ACT/EARL/SARIF assembly (docs/adr/0012) moved to
`generators/accessibility_act.py` - see
`docs/dev/generators/accessibility_act.md` - the same split
`usability`/`usability_act` established for docs/adr/0011. This module stays
the pure detection layer: it knows nothing about axe-core, ACT, EARL, or
SARIF, only WCAG criteria and the raw hint (`AccessibilityFinding.axe_hint`)
the assembly layer needs to cite the right rule.

The previous version ran axe (~90 rules) during a measurement pass that no
longer exists, and was deleted with it. This covers the criteria the captured
data supports **deterministically** - accessible names and landmark structure -
and names the ones it cannot reach.

**Why these are computable now.** Two things the storage migration and the
discovery JS already provide:

- `discover_components.js` resolves the whole accessible-name chain
  (`innerText` → `aria-label` → `aria-labelledby` → `title` → `img[alt]` →
  `svg > title`) into `text`, and the `<label>` association separately into
  `label`. A control with nothing after all of that is a finding, not a guess -
  no heuristic involved.
- `Container.landmark` plus `get_page_landmarks()` make landmark structure a
  queryable property of the page rather than something only a browser could see.

**Why the rest is still out of reach**, and why that is a capture problem rather
than a storage one: contrast needs stacked-background resolution
(`background_color` reports `rgba(0,0,0,0)` for any element whose background an
ancestor paints, which is most of them - the exact reason axe was chosen over
hand-written rules in the first place); touch-target size and spacing are
absolute thresholds against geometry measured at 800x600 with images blocked;
focus visibility and tab order need a pass that drives the keyboard.

**Findings are not stored**, matching D7. They are recomputed deterministically
from the graph every run, this document is their only consumer, and `Rule` nodes
with `DERIVED_FROM` are available for the day a second one appears. Building the
storage now would be building for one caller.

## _unique_landmarks

`banner`, `main`, `contentinfo` - the roles a page may only have one of.

`navigation` is deliberately absent: several `<nav>`s on a page is normal,
correct markup (a primary nav and a breadcrumb trail), and flagging it would
make the document wrong rather than strict. `region` likewise.

## _named_component_types

The operable types that require a name. Matched by prefix against
`component_type`, which `component_classifier.classify_component_type` already
computed at crawl time - this module does not re-derive what a control is.

`element` is excluded because it is the classifier's own "nothing identifiable
here" answer.

## accessibilityfinding

Carries `criterion` rather than just a rule name. The audience for this document
reads WCAG numbers, and "WCAG 4.1.2 Name, Role, Value" is checkable against the
standard in a way `missing-accessible-name` is not.

`axe_hint` is new: the structured value (a `_NAMED_COMPONENT_TYPES` prefix, or
a landmark role) `accessibility_act.py` needs to resolve the real axe-core
rule this finding corresponds to. Defaults to `""` so every existing call
site and test that doesn't care about it keeps working unchanged.

## _matched_named_type

Pulled out of `_needs_a_name` so the exact matched prefix is available to
`name_findings` too (for `axe_hint`), rather than the two re-deriving the
same `startswith` check against two copies of the same list.

## _needs_a_name

Restricted to the semantic discovery layer, and that exclusion is the most
debatable decision in the file.

A `cursor: pointer` catch-all element with no tag or role of its own may be an
unnamed clickable `div` - a real 4.1.2 failure - or a decorative wrapper that
merely inherits a cursor. The crawl cannot tell them apart. Reporting all of
them buries the findings that are certain; reporting none of them hides a real
class of failure. The resolution is to skip them **and count them in the
document**, so the blind spot is stated rather than silently applied.

## accessible_name

`text` or `label`. Either satisfies WCAG - an `aria-label` is a programmatic
label, so a field named that way is not a finding, and treating it as one would
make this document cry wolf on correct markup.

**`placeholder` is not a source.** It disappears as soon as the user types and
is not announced consistently. Treating it as a name is precisely the failure
`placeholder-as-only-label` exists to report, so accepting it here would delete
that rule.

Worth knowing when reading the rules: an `<input>`'s `innerText` is always
empty, so a field's name comes from `label` (or `aria-label`, which lands in
`text`). A rule that only checked `text` would false-positive on every correctly
labelled field in the site.

## name_findings

Two rules, most specific first, and one element produces at most one of them.

A nameless field that has a placeholder gets `placeholder-as-only-label`; a
nameless control with no placeholder gets `missing-accessible-name`. The fixes
differ - promote the placeholder to a label, versus invent a name that does not
exist yet - and emitting both for one element would double-count it and give a
reader two rows to reconcile.

## landmark_findings

Only pages that reported at least one landmark are judged.

A page absent from `get_page_landmarks()` has no recorded ancestry at all, and
"this page has no `main` region" and "containment was never captured for this
page" are different claims. Judging the absent pages would turn a gap in capture
into a finding against the site.

## build_findings

Returns `(findings, skipped)`. The skipped count is returned rather than logged
because it is the size of this document's own blind spot, and that belongs in
the document rather than in a terminal nobody keeps.

`AccessibilityDocument` itself - registered as `accessibility`, the scope
note, the skip count in the rendered view, and retiring the master
document's own "no WCAG audit" gap note - now lives in
`generators/accessibility_act.py`; see
`docs/dev/generators/accessibility_act.md#accessibilitydocument`.
