# generators/accessibility_act.py

## module

The `usability`/`usability_act` split (docs/adr/0011), applied to
`accessibility` (docs/adr/0012): `generators/accessibility.py` stays the
pure detection layer, this module is the ACT/EARL/SARIF assembly.

The real difference from `usability_act.py` is where the rule catalog comes
from. `usability-rules.json` is hand-authored - no pre-existing catalog
covers Nielsen heuristics. `accessibility-rules.json` is axe-core's own real
rule set, mechanically extracted once and checked in as
`generators/axe_core_rules.json`.

**How that extraction was actually done**, for anyone who needs to redo it
against a newer axe-core version: `axe.min.js` was removed from this repo in
"Pin ladybug; delete the measurement pass" (the commit before docs/adr/0012
was locked) but is still in git history at that commit's parent. Retrieving
it (`git show <that commit>~1:spiders/content/js/axe.min.js`) and loading it
in a bare Node context (`global.window = global` and a stub `document` are
enough - axe-core's UMD wrapper resolves to a CommonJS export, no real DOM
needed for rule metadata) exposes `axe.getRules()` (`ruleId`, `description`,
`help`, `helpUrl`, `tags`, `actIds`) and the internal `axe._audit.rules`
array, which is where each rule's own default `impact` actually lives -
`getRules()` doesn't carry it. No axe-core dependency, network access, or
running browser was needed at generation time, and none is needed to
*regenerate* the catalog for a newer axe-core release either.

**No live axe-core run happens anywhere in this pipeline.** The measurement
pass that used to run `axe.run()` against a live page was deliberately
removed, and reviving it is out of this ticket's scope - a
`wayfinder:task` execution ticket builds against its ADR, it doesn't reverse
an architecture decision from a different one. `accessibility.earl.jsonld`'s
findings are `generators/accessibility.py`'s own two deterministic checks
(accessible names, landmark structure), each cited against the real
axe-core rule id that checks the same thing, where one exists.

## _load_rule_catalog_data

The raw checked-in extraction, loaded fresh per call rather than cached at
import time - matches `utils/schema_validation.py`'s own
`Path(...).read_text()` convention, and 104 small dicts is not worth adding
a caching layer for.

## build_rule_catalog

`defaultConfiguration` carries both `level` (SARIF-normalized, canonical)
and `impact` (axe-core's own raw value) - docs/adr/0012 point 3 names this
exact pairing, just at the per-instance finding level; here it's the same
pairing at the rule's own default.

## _axe_rule_id

Three real, verified correspondences, no guessing:

- `no-main-landmark` always means axe's `landmark-one-main` - one check, one
  rule, no lookup table needed.
- `duplicate-unique-landmark` carries which landmark role duplicated
  (`AccessibilityFinding.axe_hint`) and looks up the role-specific axe rule
  (`landmark-no-duplicate-{banner,main,contentinfo}`) - three separate real
  axe rules, not one generic "duplicate landmark" rule, so citing the wrong
  one would be a real, checkable error, not a shrug.
- `missing-accessible-name`/`placeholder-as-only-label` both report the same
  underlying gap (no accessible name) for a control of some
  `_NAMED_COMPONENT_TYPES` type, and axe-core splits its own name-checking
  per element/role (`button-name`, `link-name`, `select-name`, ...) rather
  than offering one generic rule. `_AXE_RULE_BY_COMPONENT_TYPE` is that real
  split, ported to pragma's own coarser type vocabulary.

`"tab"` has no entry on purpose: axe-core 4.10.2 genuinely has no rule for
ARIA tab accessible names (confirmed against the full 104-rule extraction,
not assumed). Forcing a mapping to the closest-sounding rule would cite a
control type axe-core was never checking. `test_every_named_component_type_but_tab_resolves_to_a_real_axe_rule`
(`tests/test_accessibility_act.py`) is the guard against a silently
unmapped type - if a future component type is added to
`_NAMED_COMPONENT_TYPES` with no entry here, that test fails loudly instead
of the finding just vanishing.

## build_earl_document

A finding with no `_axe_rule_id` result is skipped, not mis-cited. The
caller (`AccessibilityDocument.generate`) recomputes the exclusion count by
diffing `build_findings`'s own total against `len(@graph)`, rather than this
function returning a `(document, excluded)` pair - keeps the function's
return shape identical to `usability_act.build_earl_document`'s, and the
count is cheap to recompute from data already in hand.

## build_sarif_document

Byte-identical logic to `usability_act.build_sarif_document` - the point of
ADR-0011 point 4's "severity defaults at the rule level... no remapping"
design generalizes cleanly to `accessibility`, since `level` is already
final by the time an EARL assertion exists.

## _screen

`AccessibilityFinding.where` (and therefore `subject.@id`) is either a bare
page url (landmark findings) or `"{page_url} — {path}"` (name findings).
Splitting on the first ` — ` handles both without the caller needing to
know which kind of finding it's looking at.

## _exclusion_note

Shared by both branches of `_render_accessibility_view` (all findings
excluded vs. some findings excluded) so the wording is written once. Without
this, the two branches would carry two copies of the same sentence with an
obvious risk of one getting edited and the other not.

## _render_accessibility_view

**Deduplicated by rule, not one row per instance** (docs/adr/0012 point 4) -
this *is* the migration checklist, not a separate `checklist.json`. A
reviewer needs "fix `button-name`, 6 instances across 3 screens", not six
identical-looking rows for the same underlying gap repeated per element.

The empty-graph branch has to handle both "genuinely nothing found" and
"everything found was excluded for lacking an axe correlation" - conflating
those would silently drop the exclusion count exactly when it matters most
(every finding this run produced was unciteable), so `excluded` is checked
even inside the early return.

## accessibilitydocument

Registered as `accessibility`, same registry key `generators/accessibility.py`
used before the split - no config or manifest change required anywhere else
in the pipeline. Kept after `usability` in `core/config.py`'s default list,
matching `AccessibilityDocument`'s old placement.
