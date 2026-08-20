# `risk-register` stays deterministic, annotates CycloneDX rather than duplicating it

**Status**: accepted

The ticket's three open points all resolve from a property this whole map has protected in every
prior document: determinism. Every ID and every field locked so far derives purely from
crawl-observed data or a static rule catalog — nothing queries a live external service at generation
time. A CVE database lookup would be the first exception, and it would break exactly the guarantee
every Short hash ID depends on (same crawl in, same output out).

Decided, resolving the ticket's three open points:

**1. CVE Lookup: Reserved, Not Live.** `risk-register.json` ships what's structurally observable in
v1 — outdated version strings, deprecated headers, unmaintained-looking dependency patterns —
deterministic, no network dependency. Live CVE cross-referencing (OSV, NVD, or similar) is a
**reserved** field/capability rather than part of the core generation pass, for the same reason
`coverage` reserved `roles`/`blockers` rather than fabricating them (ADR-0001): the mechanism
doesn't fit the pipeline's determinism model yet, not that it's a bad idea.

**2. Severity: SARIF `level` Plus Native CVSS, Not Either/Or.** `level` (SARIF's enum) is always
populated, for consistency with `usability`/`accessibility`'s dashboard-facing severity model
(ADR-0011/0012). An optional `cvss_score`/`cvss_vector` is populated only when a real CVE is
actually cross-referenced — CVEs are natively CVSS-scored, and remapping that into SARIF's 4-value
enum would be lossy. Mirrors `accessibility`'s exact pattern for axe-core's `impact` (ADR-0012): the
native value rides alongside the canonical cross-document one, never replaced by it.

**3. Sparse Annotation, Never a Re-listing.** `risk-register` entries exist only for services that
actually carry a flagged risk, each citing `architecture.cyclonedx.json`'s (ADR-0010) identifying
key by reference. The full third-party inventory is never duplicated — the same anti-duplication
stance every document in this map has taken since `coverage` (ADR-0001).

Depends on `architecture`'s CycloneDX inventory (ADR-0010).

Wayfinder ticket: [risk-register: lock schema, cross-reference architecture's CycloneDX inventory](https://github.com/ezequielrickert/pragma/issues/88),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
