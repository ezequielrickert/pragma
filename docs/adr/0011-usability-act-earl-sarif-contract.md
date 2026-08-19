# `usability` splits into a rule catalog, EARL findings, and a SARIF export

**Status**: accepted

The format audit's section 3.10 locks ACT Rules Format 1.1, EARL 1.0/JSON-LD, and a parallel SARIF
export for `usability`'s Nielsen-heuristic UX findings (distinct from `accessibility`'s WCAG
violations — they share tooling, not scope). Its "align severity to WCAG-EM" instruction doesn't
hold up: WCAG-EM is a pure evaluation-process methodology (sampling, scope, steps) with no
per-finding severity taxonomy of its own — its only conformance concept (A/AA/AAA) is a page-level
target, not a severity scale. This ADR locks a severity vocabulary that actually exists in the
stack, splits `usability` into three documents plus a view, and resolves the ticket's other two
open points.

Decided, resolving the ticket's three open points (plus the severity-vocabulary correction):

**1. Severity Vocabulary.** Adopt **SARIF 2.1.0's `level` enum** (`error`/`warning`/`note`/`none`)
directly — the only spec-native severity field across ACT, EARL, WCAG-EM, or SARIF. Carried into
EARL findings via a custom `level` extension property (EARL 1.0 has no native severity field of its
own). Severity defaults at the **rule** level (`usability-rules.json`'s
`defaultConfiguration.level`, mirroring SARIF's own `reportingDescriptor.defaultConfiguration.level`
model) with optional per-finding override, so `usability.sarif.json`'s export needs no remapping —
just "use the override if present, else the rule's default."

**2. Rule ID Scheme and Nielsen-Heuristic Grouping.** ACT Rules Format 1.1 mandates no ID scheme (the
W3C ACT Rules Community Group's own catalog just uses random 6-character hex, by convention, not
spec). Pragma's own rules — hand-curated, not consumed from that catalog — use semantic slugs
instead: `RULE-<heuristic-slug>-<NN>` (e.g. `RULE-loading-feedback-01`), readable and greppable
where the CG's convention optimizes for a large, crowd-sourced set humans don't need to remember by
name. ACT has no native construct for grouping rules under a higher-level heuristic (its only
grouping mechanism maps a rule *outward* to external requirements like WCAG success criteria, not
inward to a conceptual category), so each rule carries a custom `x-nielsen-heuristic` extension —
an enum of Nielsen's 10 heuristics — making the mapping machine-checkable rather than
documentation-only.

**3. `earl:mode` Usage.** Set per finding from how pragma actually produced it:
`earl:automatic` for pure pattern/heuristic detections (e.g. HAR-timing-based "no loading feedback
during a >2s wait"), `earl:semiAuto` for LLM-flagged judgment calls awaiting review, `earl:manual`
reserved for HITL-confirmed or human-authored findings via the dashboard. Kept orthogonal to
`level`: `mode` describes how the finding was produced, not how bad it is.

**4. Document Split.** `usability-rules.json` is a **rule catalog** (hand-authored, not
crawl-derived — see `CONTEXT.md`) carrying each rule's `id`, `x-nielsen-heuristic`, and
`defaultConfiguration.level`. `usability.earl.jsonld` is the real per-run **source document**: EARL
1.0/JSON-LD findings, each citing `rule_id`, `earl:mode`, `level` (per point 1), `derived_from`
evidence pointers (`interaction:<id>`/`har:<id>`/`screenshot:<id>`, the convention `prd` already
locked in ADR-0009), `coverage_ref` (ADR-0001), and an AXTree JSON Pointer reusing `tree`'s existing
locator mechanism (`x-axtree-ref`/`axtree_ref`, ADR-0003/ADR-0006) rather than a new
`screen:SCR-014#element` syntax. `usability.sarif.json` is a **projection** (`CONTEXT.md`) of
`usability.earl.jsonld`'s findings into SARIF 2.1.0 — `ruleId`/`level`/`message`/`location`
populated mechanically, for CI/tooling consumption, never hand-edited. `usability.md` is the
**view document**, rendered from both `usability-rules.json` and `usability.earl.jsonld`.

Wayfinder ticket: [usability: lock contract (ACT Rules + EARL + SARIF)](https://github.com/ezequielrickert/pragma/issues/75),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
