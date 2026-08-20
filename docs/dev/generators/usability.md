# `generators/usability.py`

## module

D7: Nielsen-heuristic findings, computed rather than judged.

**No model call, deliberately.** A heuristic evaluation the model performs
is an opinion, and an opinion citing no evidence has no business in a
document a rebuild gets planned from. Every rule here is deterministic and
every finding carries the page and element it came from, so a reader who
disagrees can go and look.

**Findings are prescriptive.** The project's goal is to refactor the
experience, not reproduce it, so each finding says what the rebuild should
do rather than only what the current system does.

## Finding

`severity` drives ordering only. It is a judgement about how much a defect
costs a user, and it is deliberately coarse - three levels, not a score,
because a number would imply a precision none of these rules have.

## _semantic_type_hints

Vocabulary in a field's `name` or `placeholder` implying a more specific
input type than plain text. Bilingual because the applications this tool
targets are.

Matched against `component_type`, not `input_type`: the ledger does not
return `input_type`, but `classify_component_type` already folds it into
its label (`text field (email)`), so `text field (text` is the signal that
a field was left generic.

## _normalize

Folds accents rather than deleting them. An earlier version stripped
non-ASCII outright, which turned `"móvil"` into `"mvil"` - and `"movil"`
does not appear in that. The hint list happened to also contain `"tel"`,
so the test passed for the wrong reason and the real miss stayed hidden.
Same NFKD decomposition `component_classifier._normalize` already uses.

## inconsistent_family_styling

The highest-value rule here, and it exists **only because families
exist**. Three different shades of primary button is not something anyone
spots by eye across a large application; with the clustering already done,
it is one grouping away.

Note this rule survives without the measurement pass: it compares colours
against each other, and a relative comparison holds even when every
absolute value was measured through a browser with images blocked.

## inconsistent_action_naming

Two controls firing the same endpoint under two different labels. A user
pays for that inconsistency, and it is invisible without the endpoint to
group the controls by - which is what `InferredRequest.triggered_by` gives.

## missing_semantic_input_type

Costs a user the right mobile keyboard and the browser's own validation,
both free with the correct `type`. Breaks after the first match so one
field named `fecha_email` reports once rather than twice - it needs one
type, and listing two would leave the reader to pick.

## unexplained_disabled_controls

Reports only when geometry exists, and treats missing geometry as
"explained". The asymmetry is deliberate: a false "no explanation" wastes
a reviewer's time on a control that was fine, while a missed one costs
nothing, since this is the lowest-severity rule here.

`_NEARBY_TEXT_PX` is generous for the same reason.

## flow_findings

One rule now, `dead-end-screen`: a state the crawl reached and never left.
The recommendation points at the coverage document on purpose - a screen with
no observed exit and a screen whose exits were never tried look identical
here, and acting on the second would be wrong.

**`unattributable-outcome` was deleted, not disabled.** It fired on
transitions whose outcome was `"mixed"`, meaning one control led to several
screens whose requests disagreed and there was no way to tell which request
belonged to which move. That was true when requests were pooled onto the
`Component`. A `Request` now hangs off its own `Interaction` with
`visit_id`/`step_seq`, so `user_flows._request_outcome` returns only
`OK`/`ERROR`/`UNKNOWN` and each click of one control keeps its own result.

The rule described a limitation of the storage layer; the storage layer
stopped having it. A branch that can never be taken is worse than no rule at
all - it reads like coverage.

## build_findings

Since ticket #105, this module holds detection logic only - the
registered `DocumentGenerator` (`UsabilityDocument`) moved to
`generators/usability_act.py`, which owns the ACT/EARL/SARIF
serialization (docs/adr/0011) and the empty-case wording ("the audit was
*narrow*, not that the application is usable" - six deterministic rules
finding nothing means six rules found nothing).
