## Resolution

Investigated the installed `ladybug` package (`.venv/lib/python3.11/site-packages/ladybug`,
version `0.19.1`, `Database.get_storage_version() == 43` — confirmed live, not just believed)
and pragma's own wrapper in `database/ladybug/`.

### What `ladybug` actually is

`ladybug` is an embedded property-graph database (the Kùzu API surface under a different name:
`Database`/`Connection`, Cypher-subset `execute()`, `CREATE NODE TABLE`/`CREATE REL TABLE` DDL,
a native `_lbug` C library). It has no fixed built-in "interaction"/"edge" schema of its own —
every node and relationship table (`Interaction`, `PERFORMED`, `TRIGGERED`, etc.) is defined by
**pragma's own DDL** in `database/ladybug/schema.py`. So "does Ladybug have an extensible
metadata field on interactions" is really two separate questions, one about the storage engine
and one about pragma's schema on top of it.

### storage_version 43 vs. pragma's table schema — these are different things

`storage_version` is the on-disk file/page/WAL binary format the native `_lbug` engine writes —
it changes only when the `ladybug`/Kùzu engine itself is upgraded (e.g. `0.19.1` → `0.20.0`
would likely bump it), never when a caller adds a column to their own table. Confirmed: pragma's
`raw_query.py` deny-lists `ALTER` among recognized DDL/mutating keywords for its read-only-query
guard, meaning `ALTER TABLE ... ADD COLUMN ...` is a real, supported statement in this engine's
query surface — the standard Kùzu schema-evolution primitive, distinct from a storage-format
bump. **No format/version bump is needed to add a `blocked` flag to `Interaction`.**

### Current `Interaction` schema (`database/ladybug/schema.py`)

```
CREATE NODE TABLE IF NOT EXISTS Interaction(
    id SERIAL PRIMARY KEY,
    action STRING DEFAULT '',
    value STRING DEFAULT '',
    source_path STRING DEFAULT '',
    visit_id STRING DEFAULT '',
    step_seq INT64 DEFAULT 0);
```

No JSON/MAP catch-all column exists on `Interaction` (contrast with `Page.metadata`, which
*is* `MAP(STRING, STRING)` — that pattern exists elsewhere in this schema but wasn't extended to
`Interaction`). So there is no free extensibility slot to reuse without a DDL change — but the
DDL change needed is an ordinary column add, not a schema redesign. Two new columns cover the
ticket's example (`blocked: true`, `blocked_reason: "POST"`):

```
blocked BOOLEAN DEFAULT false,
blocked_reason STRING DEFAULT ''
```

`Interaction` already links to `Request` via `TRIGGERED (FROM Interaction TO Request)` for
requests that really fired. A blocked mutation never reaches the network layer (Playwright's
`page.route` handler intercepts and fulfills synthetically before the request goes out), so it
produces no `Request` node and no `TRIGGERED` edge — the two new scalar columns on `Interaction`
itself are what carries "this would have mutated, and here's what kind" instead of trying to
force a phantom `Request`/`TRIGGERED` pair for a call that never happened. `action`/`value` on
the same node already carry what was clicked and with what value, so the addition is minimal:
just the fact and the reason it was blocked.

### Migration / backward compatibility for existing `.lbdb` files

`LadybugGraphStore.connect()` (`database/ladybug/store.py`) replays the *entire* `DDL` string on
every connect via `CREATE NODE/REL TABLE IF NOT EXISTS` — idempotent for new tables, but a no-op
for a table that already exists on disk. An old `.lbdb` file's `Interaction` table would **not**
gain the new columns automatically just by pointing new pragma code at it; `IF NOT EXISTS`
doesn't add columns to an existing table. This repo currently has no migration mechanism beyond
that blanket DDL replay — no precedent to follow, so implementation ticket #62 has to add one:
after the `CREATE ... IF NOT EXISTS` replay, run `ALTER TABLE Interaction ADD COLUMN blocked
BOOLEAN DEFAULT false` and the same for `blocked_reason`, guarded so it only runs once (Kùzu's
`ALTER TABLE ADD COLUMN` errors if the column already exists — the guard needs a schema-inspect
check, e.g. via `raw_query.py`'s `schema_card()` surface, or a try/except swallowing the
"column already exists" error, whichever `_cypher.py`'s existing error-handling conventions
favor). On read: a row written before the migration and a row written after both work
identically once the column exists with its `DEFAULT` — Kùzu backfills existing rows with the
declared default when `ALTER TABLE ADD COLUMN` runs, so old interactions simply read as
`blocked = false`, which is the correct semantic (they weren't blocked, immutable mode didn't
exist yet). No reader breaks; nothing needs versioned schema branching in query code, since every
`Interaction` row has the column after one successful connect.

### What ticket #62 needs to change

- `database/ladybug/schema.py` — add `blocked BOOLEAN DEFAULT false, blocked_reason STRING
  DEFAULT ''` to the `Interaction` table in `_OBSERVATION_DDL`, plus a same-file comment
  explaining the two columns the way every other field there is annotated.
- `database/ladybug/store.py::connect()` — after the existing `conn.execute(DDL)` call, run the
  one-time `ALTER TABLE Interaction ADD COLUMN ...` migration for databases opened before this
  ticket, guarded against re-running on a database that already has the columns.
- `database/ladybug/component.py::record_component_interaction()` (or a new sibling method, e.g.
  `record_blocked_interaction()`, if the blocked case shouldn't share the navigation-oriented
  `RESULTED_IN` write path) — accept and set `blocked`/`blocked_reason` in the `CREATE
  (i:Interaction {...})` params.
- The recording call site itself lives in the mode-gate handler the parent map (#55) already
  grounded in `spiders/browser/crawl4ai_crawler/hooks.py`'s `page.route` router — that handler
  calls into the graph store when it intercepts a blocked mutation, the same way
  `_maybe_abort_media_request` calls `route.abort()`.
- No `storage_version` bump, no `ladybug` package version bump, no format-version branching in
  any reader.

Branch: `research/59-ladybug-blocked-mutation-schema` (throwaway, not merged to `dev`).
