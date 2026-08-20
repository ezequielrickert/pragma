# `change-log` diffs per-entity, exactly the entities Short hash already IDs

**Status**: accepted

The ticket's own three open points all resolve directly from conventions this map already locked:
every entity worth diffing already has a deterministic Short hash ID (`SCR-`/`REQ-`/`EP-`/`MOD-`/
`CH-`/`MSG-`, `CONTEXT.md`), and `evidence-log` (ADR-0017) already established that not every
citation string is stable across runs. No external standard to verify against — this is pragma's
own document, decided from what's already on the books.

Decided, resolving the ticket's three open points:

**1. Diff Granularity: Per-Entity, Scoped to Short-Hash IDs.** `change-log.json` diffs every entity
kind carrying a Short hash ID, and only those — `interaction:`/`har:` citations from `evidence-log`
are excluded, since ADR-0017 already established their Kùzu `SERIAL` ids aren't stable across
re-crawls; diffing them would compare noise, not signal. A whole-document diff can only say "`prd`
changed somehow"; per-entity keyed by an ID that's already deterministic says exactly which
requirement.

**2. Three-Way Split, Forced by How the IDs Are Built.** `newly_discovered` (ID present this run,
absent the last), `no_longer_observed` (ID present last run, absent this), `changed` (same ID, a
non-identity field differs). This isn't a free design choice: every Short hash is derived from an
entity's identity-defining fields (`SCR-<hash>` from the route, `REQ-<hash>` from `ears_pattern` +
`trigger` + `target`, `EP-<hash>` from `method` + `host` + `path_pattern`), so an entity whose
identity-defining fields change doesn't keep its ID — it becomes a different one, surfacing as a
`no_longer_observed`/`newly_discovered` pair rather than a `changed` entry. `changed` only ever
means the identity held and some other field moved (a requirement's `confidence` upgraded, an
endpoint's `response_schema` evolved). Recorded as a general property of Short hash IDs in
`CONTEXT.md`, not just this document's own quirk, since anything else that ever compares one of
these IDs across two points in time inherits the same behavior.

**3. Source Document, Not Rule Catalog.** `change-log.json`'s content is explicitly crawl-derived —
a comparison of two specific runs — the direct opposite of `CONTEXT.md`'s **Rule catalog**
definition ("fixed for a given rule-set version, not derived from any crawl"). The diffing algorithm
can be static code; the emitted document is a genuine per-run-pair source document. Embeds
`run_id_from`/`run_id_to` (the two most recent runs by default), rendered to `change-log.md` — the
same source/view split every other document in this map already follows.

Wayfinder ticket: [change-log: lock cross-run diff schema](https://github.com/ezequielrickert/pragma/issues/83),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
