# `confidence-summary` aggregates by reference, stays per-run, feeds the dashboard's tile

**Status**: accepted

The last ticket in this map's new-document wave, and it resolves entirely by delegating to what's
already locked rather than inventing anything new: the map's own no-duplicate-views stance decides
the aggregation shape, `dashboard`'s existing tile decides the consumption question, and
`change-log`'s own worked example — a requirement's confidence upgrading — already claimed the
cross-run-trend job before this ticket could.

Decided, resolving the ticket's three open points:

**1. Derived Rollups Only, Never Re-Emitted Values.** `confidence-summary.json` computes aggregates
per source document — percentages, counts, distributions — citing the source by reference, never
restating individual per-entity confidence values. Re-emitting them would be the exact duplicate-view
anti-pattern this whole map exists to eliminate, one document away from where the rest of it landed.

**2. `dashboard`'s Tile Now Reads From This.** `dashboard`'s landing page (ADR-0016) already computes
a requirement-confidence split tile directly from `prd`'s raw data. Once `confidence-summary.json`
exists, it's computing exactly that same rollup — two places deriving the same aggregate is a
duplicate-*computation* problem, parallel to duplicate-view. `dashboard`'s ADR-0016 is amended: the
tile now reads from `confidence-summary.json` instead of recomputing inline. The tile's shape and
meaning don't change, only its source. This doesn't extend to `dashboard`'s other tiles (pages,
components, endpoints) — those are objective observation tallies, not confidence-shaped data, and
correctly stay `dashboard`'s own direct queries.

**3. Per-Run Snapshot, Not a Cross-Run Tracker.** `confidence-summary` captures the current run's
confidence distribution only. Cross-run confidence *trends* are already `change-log`'s job by
design — ADR-0019 named "a requirement's `confidence` upgraded" as its own worked example of what a
`changed` entry captures. Building trend-tracking into `confidence-summary` too would duplicate a
job `change-log` already owns.

Depends on `prd` (ADR-0009), `usability`/`accessibility` (ADR-0011/0012), `data-model` (ADR-0008),
and `dashboard` (ADR-0016, amended here).

Wayfinder ticket: [confidence-summary: lock cross-document confidence aggregation contract](https://github.com/ezequielrickert/pragma/issues/93),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
