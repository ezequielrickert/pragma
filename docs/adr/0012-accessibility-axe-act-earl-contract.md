# `accessibility` consumes axe-core directly, EARL findings, migration checklist folds into the view

**Status**: accepted

The ticket asks whether `usability`'s ACT Rules + EARL/JSON-LD foundation (ADR-0011) holds for
`accessibility`'s WCAG violations too, sourced from axe-core rather than hand-authored Nielsen
heuristics, and what shape a "don't reintroduce this violation" migration checklist takes. axe-core
turns out to change the picture in three concrete ways: it has a native severity field usability's
stack never had, its own rule set only partially maps onto published ACT rules, and ACT already has
a native field for exactly the WCAG-grouping problem usability had to solve with a custom
extension. This ADR locks the rule source, the WCAG grouping mechanism, the severity vocabulary,
and the checklist shape.

Decided, resolving the ticket's two open points:

**1. Rule Source: axe-core Directly, Not a Hand-Authored ACT Catalog.** `accessibility-rules.json`
is a **rule catalog** (`CONTEXT.md`) mechanically extracted from axe-core's own rule metadata —
axe-core's slug rule IDs (`color-contrast`, `image-alt`), not invented pragma IDs. axe-core is a
registered ACT-conformant implementation and its own docs maintain a partial rule-ID mapping table
to published ACT rules (e.g. `color-contrast` → ACT `afw4f7`), but that coverage is incomplete.
Rather than hand-author an ACT-only catalog covering just the mapped subset — the way
`usability-rules.json` had to, since no pre-existing catalog covers Nielsen heuristics —
`accessibility-rules.json` consumes axe-core's full rule set, citing the ACT rule ID as an optional
field only where Deque's mapping table confirms a correspondence. axe-core is the actual detection
engine that runs at crawl time; discarding its broader real coverage for the sake of ACT-only
purity would trade working detection for formal compliance with no practical benefit.

**2. WCAG Grouping via ACT's Native Accessibility Requirements Mapping.** Each rule's WCAG
success-criterion grouping uses ACT Rules Format 1.1 §4.4 ("Accessibility Requirements Mapping") —
a real, spec-native field for citing external requirements a rule's failure violates — populated
from axe-core's own `wcag2a`/`wcag111`-style tags. No custom extension needed, unlike `usability`'s
`x-nielsen-heuristic`: ACT already has a construct for this because "which WCAG success criterion
does this violate" is exactly what ACT Rules Format was designed to answer, where "which Nielsen
heuristic does this violate" was never in scope for the spec.

**3. Severity: Normalize to SARIF's `level` at Ingestion.** axe-core's native `impact` field
(`minor`/`moderate`/`serious`/`critical`) is mapped to SARIF 2.1.0's `level` enum
(`error`/`warning`/`note`/`none`) immediately on ingestion, not carried through as the canonical
value. `usability` and `accessibility` feed one dashboard; a reviewer comparing findings side by
side benefits more from one consistent severity vocabulary across both documents than from
`accessibility` alone staying maximally faithful to axe-core's native terms. The raw `impact` value
isn't discarded — `accessibility.earl.jsonld` carries it as a secondary provenance citation
alongside the canonical `level`.

**4. Migration Checklist: No New Document.** The ticket's "don't reintroduce this violation"
checklist is `accessibility.md` itself, organized around findings deduplicated by rule (via the
WCAG grouping in point 2), each row showing instance count and affected screens — not a separate
`checklist.json`. A dedicated checklist file would duplicate what `accessibility.earl.jsonld` and
`accessibility.sarif.json` already carry, the exact duplicate-view anti-pattern this map exists to
eliminate. Anything a machine needs from this (e.g. a CI gate against reintroducing a fixed
violation) is what SARIF baseline/suppression already handles natively — no new mechanism required.

**5. Document Split.** `accessibility-rules.json` (rule catalog, point 1) + `accessibility.earl.jsonld`
(per-run source document — `rule_id`, `earl:mode`, `level`, raw `impact` citation, `derived_from`
evidence pointers per ADR-0009's convention, `coverage_ref` per ADR-0001, and an AXTree JSON Pointer
reusing `tree`'s locator mechanism per ADR-0003/ADR-0006 — the same shape `usability.earl.jsonld`
locked in ADR-0011) + `accessibility.sarif.json` (SARIF **projection**, `CONTEXT.md`) +
`accessibility.md` (the **view document**, doubling as the migration checklist per point 4).

Wayfinder ticket: [accessibility: lock contract (a11y violations, migration checklist)](https://github.com/ezequielrickert/pragma/issues/76),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
