# `coverage.json` ships only what the crawler can measure today

**Status**: accepted

The format audit's example `coverage.json` includes `roles`, `blockers`, and a full `module_coverage`
breakdown alongside the pages/interaction/endpoint numbers `generators/coverage.py` already computes.
Of those, only pages, interaction, endpoint count, and a saturation curve (derivable from
`Interaction.step_seq`, already stored) are backed by real crawler data — the crawler never signs in
(single anonymous role), has no blocker-type detection (login/captcha/paywall) anywhere in the
codebase, and has no module-detection pass (that's `architecture`'s graph-metrics ticket, #72,
itself blocked on `export`).

Decided: `roles` and `blockers` are reserved fields, present but minimally populated
(`roles: ["anon"]`, `blockers: []`) rather than omitted, so later documents can reference the field
name today without a breaking schema change once role/blocker detection exists. `module_coverage`
is reserved empty (`[]`) for the same reason, keyed to whatever module-ID scheme `architecture`/
`export` eventually settle on rather than a throwaway heuristic invented here. UI-state breakdown
(empty/error/loading/forbidden/paginated) is dropped entirely, not reserved — no instrumentation
path for it exists yet, so a reserved slot would be a field with no plan behind it.

Also decided: `coverage.json` replaces `render_coverage_banner()`'s live `graph_store` reads.
Every generated document's banner becomes a template render of `coverage.json`'s numbers,
computed once per run — the alternative (banner keeps its own direct query, `coverage.json` computes
the same numbers separately) is the duplicate-view anti-pattern this whole effort exists to remove,
just moved one layer down.

Wayfinder ticket: [coverage: lock schema and contract](https://github.com/ezequielrickert/pragma/issues/65),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
