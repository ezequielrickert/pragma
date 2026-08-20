# `content-inventory` cites `catalog`'s component granularity, owns its own legal flag

**Status**: accepted

The ticket's three open points resolve against granularity `catalog` already established and a
distinction between two axes — personal-data collection versus legally-mandated copy — this map
hasn't drawn yet because nothing before this needed to.

Decided, resolving the ticket's three open points:

**1. Granularity: Component-Primary, Screen as Location Context.** Entries cite the specific
component instance where text was observed (`catalog`'s `x-observed-variants`, ADR-0006) as primary
organization, with the screen (`SCR-<hash>`) riding along for location context. A flat per-screen
bag of text would lose the structural precision `catalog` already established — copy lives inside a
specific component, not a whole screen undifferentiated.

**2. `is_legal`/`requires_review`: Its Own Flag, a Different Axis From DPV.** `data-model`'s DPV/PII
annotations (ADR-0008) answer "is this data field's *value* personal data being collected." This
document answers a different question: "is this piece of *static displayed copy* legally-mandated
text" — a disclaimer, a required regulatory notice, terms-of-service language. DPV's vocabulary is
scoped to data processing and doesn't naturally extend to static webpage copy, so `content-inventory`
carries its own native `is_legal`/`requires_review` flag rather than force-fitting a DPV term onto
something DPV was never built to describe.

**3. Overlap With `glossary`: The Cross-Reference Completes.** `glossary` (ADR-0020) already set up
a forward-pointing citation to this document's copy occurrences. `content-inventory` entries that
also function as recurring business concepts cite `glossary`'s `TERM-<hash>` back — the same
bidirectional-pointer pattern, no exclusive ownership in either direction. `glossary`'s ADR is
amended to firm up its forward reference now that this ticket has a number.

Wayfinder ticket: [content-inventory: lock schema for copy/microcopy/legal text capture](https://github.com/ezequielrickert/pragma/issues/89),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
