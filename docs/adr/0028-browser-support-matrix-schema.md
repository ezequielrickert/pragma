# `browser-support-matrix` separates observed evidence from business reasoning

**Status**: accepted

The ticket's own framing — "tied to real business decisions," not a generic compatibility table —
already draws the line this document needs: what a crawler can observe and what only a human knows.
This map already has vocabulary for exactly that split (`prd`'s confidence categories and
`hitl_status`, ADR-0009), so the schema reuses it rather than inventing a parallel one.

Decided, resolving the ticket's three open points:

**1. Two-Tiered Detection.** Technical evidence — polyfills, vendor-prefixed CSS, user-agent-sniffing
code found in the crawled site's own pages — is genuinely **observed**; a crawler can find these.
The business reason behind a constraint ("a major client's procurement system requires IE11") is not
inferable from the site at all — it's an external fact only a human knows. Each entry carries the
observed technical constraint plus an optional `business_reason` field, unset by default, filled in
by a human reviewer later — reusing `prd`'s `hitl_status` review-workflow pattern (ADR-0009) rather
than a new HITL mechanism.

**2. Format: Pragma-Native Document, Browserslist Query Syntax for Values.** Browserslist's own
format is a forward-looking query language for *specifying* build targets (`"IE 11"`, `"last 2
versions"`) — it has no fields for evidence, confidence, or business reasoning, so it's the wrong
shape for a document that records observations, not targets. `browser-support-matrix.json` is
pragma-native at the document level, but each constraint's browser/version value is expressed in
Browserslist's own query-string syntax (`browserslist_query: "IE 11"`) — compatible with existing
tooling (autoprefixer, etc.) that already parses these strings, without adopting Browserslist's
document shape wholesale.

**3. Relationship to `performance-baseline`: Citation, Not Duplication.** A `browser-support-matrix`
entry can cite which `performance-baseline` templates (`template_hash`, ADR-0026) its constraint
affects, flagging where legacy-browser support changes what "acceptable" performance looks like —
without duplicating `performance-baseline`'s threshold data. Same citation-not-duplication posture
every cross-document relationship in this map has used since `catalog`'s `x-tokens` (ADR-0006).

Wayfinder ticket: [browser-support-matrix: lock schema for legacy browser constraints](https://github.com/ezequielrickert/pragma/issues/92),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
