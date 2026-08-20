# `decisions.adr` documents inferred/assumed classifications, optional in llms.txt

**Status**: accepted

The ticket's three open points all resolve directly from conventions this map already locked: `prd`
already draws exactly the confidence line this document needs (ADR-0009), and `llms.txt`'s
`## Optional` section already exists for exactly this kind of secondary-but-genuine value
(ADR-0015). Nothing here needed a new threshold or a new placement rule invented from scratch.

Decided, resolving the ticket's three open points:

**1. Trigger: `inferred`/`assumed`, Not `observed`.** A `decisions.adr` entry is emitted for every
entity classified `inferred` or `assumed` under `prd`'s existing confidence vocabulary (ADR-0009) —
never for `observed` entities, since "observed" already means directly verified from crawl data,
with no judgment call to explain. Reuses a threshold that already exists and means precisely this,
rather than inventing a second confidence-adjacent concept.

**2. ID Scheme: MADR's Own Numbering, Entity Citation as Cross-Reference.** Each entry is a
sequentially-numbered MADR file within a per-run `decisions.adr/` directory
(`0001-button-classified-destructive.md`), the same numbering convention this repo's own
`docs/adr/` already uses — MADR's native identity mechanism, not routed through this map's Short
hash family. The entity a decision is about (`REQ-<hash>`, `EP-<hash>`, whichever kind applies) is
cited in the entry's body as a cross-reference. These are pragma's own crawl-time judgment calls
about how to classify something, not a stable identity for something observed on the legacy site —
a different kind of thing than what Short hash IDs identify.

**3. Optional in `llms.txt`.** Genuinely useful to a rebuild team — it lets them understand or
challenge an ambiguous classification rather than take it on faith — but secondary to the entity it
explains. Belongs in `## Optional` (ADR-0015), matching that section's own stated purpose: links an
agent can skip when a shorter context is needed.

Wayfinder ticket: [decisions.adr: lock MADR contract for the pipeline's own inference decisions](https://github.com/ezequielrickert/pragma/issues/87),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
