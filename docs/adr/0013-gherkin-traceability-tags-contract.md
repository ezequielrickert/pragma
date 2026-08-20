# `gherkin` locks a traceability-tag vocabulary and Outline dedup convention

**Status**: accepted

The ticket's own example tags (`@REQ-0042`, `@EP-017`, `@MOD-facturacion`) predate two tickets that
have since resolved differently: `prd` locked `REQ-<hash>` (ADR-0009), not a sequential counter, and
`architecture`'s graph-metrics ticket (ADR-0007) locked how a module is *derived* but never a
literal ID string. Neither the graph's real `Endpoint` id (`"METHOD host/path_pattern"` — spaces and
braces, unusable as a Gherkin tag) nor `Modulo` has a tag-safe format yet. This ADR locks both,
alongside the tag vocabulary and `Background`/`Scenario Outline` conventions the ticket asked for.

Decided, resolving the ticket's two open points (plus the two ID formats neither prior ticket
locked):

**1. Endpoint Tag ID (`EP-<hash>`).** A deterministic hash of `method + host + path_pattern` — the
graph's own `Endpoint` composite key (`database/ladybug/ids.py`) — matching the determinism
reasoning `SCR-<hash>` (ADR-0003) and `REQ-<hash>` (ADR-0009) already established: stable across
runs, no counter drift, safe as a bare Gherkin tag where the raw graph id isn't.

**2. Module Tag ID (`MOD-<slug>`/`MOD-<hash>`).** `MOD-<slug>` for a path-prefix-derived module
(readable — `MOD-facturacion`); `MOD-<hash>` for a module with no natural name (a Leiden-detected
community with no dominant path prefix). `gherkin` is the first document that needs a concrete
Module ID string rather than just the derivation rule ADR-0007 locked, so it locks the format here —
the same relationship `tree` has to every document that cites `SCR-<hash>`.

**3. Tag Vocabulary.** `@REQ-<hash>` and `@confidence:<observed|inferred|assumed>` (reusing `prd`'s
exact enum, ADR-0009) are **required** on every generated scenario — traceability back to a
requirement and a trust signal are the point of this ticket. `@EP-<hash>` and `@MOD-<slug|hash>` are
**optional** (a scenario doesn't necessarily touch an API, and a module may not yet be derivable).
`@SCR-<hash>` (ADR-0003) is added as a new **optional** namespace beyond the ticket's own example —
a scenario describes a UI walkthrough, and every other traceable document in this map already cites
screens.

**4. `Background` / `Scenario Outline` Convention.** `Scenario Outline` + `Examples` is used
specifically to deduplicate structurally-identical repeated observations — the same interaction
pattern observed multiple times with only concrete values differing becomes one `Outline` with N
`Examples` rows, not N near-duplicate `Scenario`s, mirroring `tree`'s `template_hash` dedup
(ADR-0003). `Background` is reserved for setup steps common to every scenario in one `Feature` file
(e.g. an authentication precondition), never used to hide dedup that belongs in an `Outline`.

**5. Short-Hash Algorithm** (amendment, ADR-0015). `EP-<hash>` and `MOD-<hash>` were both defined
as "a deterministic hash" without saying which algorithm. Pinned to `sha1(...)[:10]`, matching the
algorithm already used for exactly this purpose elsewhere in the codebase
(`spiders/content/component_matching.py`) — see `CONTEXT.md`'s **Short hash** entry.

Wayfinder ticket: [gherkin: design traceability-tag vocabulary](https://github.com/ezequielrickert/pragma/issues/77),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
