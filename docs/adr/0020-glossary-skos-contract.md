# `glossary` uses SKOS's native relationships, a pragma extension only for evidence

**Status**: accepted

The ticket's three open points split cleanly along a line SKOS itself already draws: its
`broader`/`narrower`/`related` vocabulary was built for exactly the term-relationship problem this
document has, but SKOS has no provenance field at all, so evidence citation needs the same pragma
extension pattern every other document in this map already uses.

Decided, resolving the ticket's three open points:

**1. Term ID: `TERM-<hash>`.** A new **Short hash** member (`CONTEXT.md`) — a deterministic hash of
the term's normalized `skos:prefLabel` — so the same business term observed across two crawl runs
mints one concept, not two. Matches the pattern every prior ticket needing a new entity kind has
followed (`CH-`/`MSG-` from `asyncapi`, ADR-0018).

**2. Relationships Native, Evidence Extended.** `skos:broader`/`skos:narrower`/`skos:related` cover
term-to-term relationships as-is — no pragma extension needed, that's precisely what SKOS was
designed for. Evidence citation — which screens or copy a term was observed in — has no SKOS
equivalent, so it reuses the established pragma extension shape: `derived_from` evidence pointers
(`interaction:<id>`/`har:<id>`/`screenshot:<id>`) plus `tree`'s AXTree JSON Pointer for element-level
provenance (ADR-0003/ADR-0006).

**3. Overlap Is Cross-Reference, Not Exclusive Ownership.** `glossary` owns strings that function as
reusable domain vocabulary — the test is whether a term recurs across contexts as a meaningful
business concept, not whether it's a one-off field name or literal string. A term cross-references
`data-model` fields/enum values where one corresponds (e.g. `"factura tipo C"` citing `invoice.tipo`'s
`"C"` enum value, ADR-0008) and, once `content-inventory` (#89) resolves, its copy occurrences — by
pointer, the same way `catalog`'s `x-tokens` cites `tokens.json` rather than duplicating token data
(ADR-0006). The same string can legitimately live in more than one document for different reasons;
forcing single ownership would just relocate the duplicate-view problem rather than solve it.

Wayfinder ticket: [glossary: lock SKOS/JSON-LD domain-term contract](https://github.com/ezequielrickert/pragma/issues/84),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
