# `evidence-log` indexes only what has no other resolution path

**Status**: accepted

The ticket frames `evidence-log` as indexing HAR entries, screenshots, and DOM/AXTree snapshots so
every `derived_from` pointer already emitted across this map (`prd`'s ADR-0009, `usability`'s
ADR-0011, `accessibility`'s ADR-0012, `flows`' ADR-0014) resolves to something real. Checking the
actual codebase narrows that scope: two of the three evidence kinds already have a resolution path,
and the two that don't turn out to use unstable IDs, which settles the ticket's own open question
about cross-run stability before it needs to be asked.

Decided, resolving the ticket's three open points:

**1. Per-Run, Not Cross-Run.** `evidence-log.jsonl` is one file per crawl run, named/keyed by
`run_id` (a real timestamp string, `core/engine.py`'s `_timestamp()` — not something this ticket
invents). `Interaction` and `Request` — the graph tables backing `interaction:<id>` and `har:<id>`
— both use Kùzu's `SERIAL PRIMARY KEY` (`database/ladybug/schema.py`), an auto-increment counter
local to one database instance. `interaction:42` from one crawl and `interaction:42` from a
re-crawl are not the same interaction. A cross-run accumulating index would need a compound
`(run_id, local_id)` key to avoid silent collisions; a per-run file gets that for free.

**2. Scope: `interaction:`/`har:` Plus a Reserved `screenshot:`.** `interaction:<id>` and
`har:<id>` are indexed because they exist *only* as graph nodes with no portable file
representation — a reader outside the pipeline (or without Kùzu access) has no way to resolve them
otherwise. AXTree/DOM snapshots are **not** re-indexed: `tree` already made them resolvable via
`SCR-<hash>` plus a per-leaf `x-axtree-ref` JSON Pointer (ADR-0003), and duplicating that here would
be exactly the duplicate-view anti-pattern this map exists to eliminate. `screenshot:<id>` ships as
a **reserved** kind — present in the schema, empty until screenshot-capture instrumentation exists
(none does today, confirmed against the codebase) — following the same reserved-field precedent
`coverage` set for fields with no crawler instrumentation behind them yet (ADR-0001).

**3. Row Shape: a Lightweight Index, Not a Duplicate.** Each row: `id` (the exact citation string
already in use elsewhere — `"interaction:42"`, `"har:17"`), `kind` (`interaction`/`har`/`screenshot`),
`run_id`, and one short human-readable summary. Not a copy of the graph node's full field set
(`method`, `status`, `action`, `value`, ...) — the graph stays the authoritative full-detail source,
queried directly (`CONTEXT.md`'s "The graph"), the same division of labor `export.json` already has
with it (ADR-0002). `evidence-log` proves a pointer resolves and gives enough context to know what
it's pointing at; it doesn't re-store what it's pointing at.

Wayfinder ticket: [evidence-log: design JSONL append-only evidence index](https://github.com/ezequielrickert/pragma/issues/81),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
