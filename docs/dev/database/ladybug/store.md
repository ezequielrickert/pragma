# database/ladybug/store.py

## module

`LadybugGraphStore` - the one class the rest of the project talks to for
storage, assembled from twelve mixins over `schema.py`'s DDL.

**One database per site, not one shared file.** `site` used to be the first
argument of all 41 store methods and a column on all 21 DuckDB tables,
existing only so a single shared database could tell sites apart -
and `Engine.from_config` derives exactly one `site` per run and never varies
it. A database per site removes the argument and the column: `clear_site()`
becomes `reset()`, and a purging run reclaims disk instead of leaving
freed-but-unshrunk pages behind the way `data/pragma.duckdb` did (42MB for a
20-page crawl, plus a 7.4MB WAL).

**Two registry names, one class.** `ladybug` and `memory` differ only in
whether a directory is passed. They stay two names because that is what
`pragma.yaml`, `cli.py --graph-store` and the wizard already answered to, and
renaming them would break every existing config for no gain.

**There is no `GraphStore` ABC.** `core/interfaces.py` is down to `Agent` plus
re-exported data contracts, so this class is duck-typed against the methods
its callers use. That is honest while one implementation exists and is a real
cost the moment a second one is wanted - the interface has to come back first.
It is also why adding a read method means updating the fake stores in
`tests/`, which is a feature: it makes the coupling visible.

## _resolve_path

`<directory>/<slug(site)>.lbdb`, or Ladybug's in-memory sentinel (`""`) when
`directory` is `None`.

A bare `site` is usually a host (`austral.edu.ar`) that needs no slugging at
all, and it goes through `slugify` anyway - so a site name containing
something a filesystem rejects is handled the same way here as in every other
per-site filename this project writes, rather than only here.

## connect

Establish the connection, run the DDL idempotently, write the `Site` header
row. Returns early if already connected, so it is safe to call from
`_call`'s lazy path and from an explicit caller in the same run.

The DDL runs on every connect rather than once at creation: `CREATE ... IF NOT
EXISTS` is cheap, and it means a database created by an older version picks up
any table added since without a migration step.

## _touch_site

Creates the `Site` row or refreshes `last_crawled`. `first_crawled` is written
once and never overwritten - the same "first sighting is permanent" rule
`record_edge`'s `first_seen_run` follows, so a resumed crawl cannot rewrite
history it did not observe.

## close

Releases the connection, safe to call when never connected. Both the
`Connection` and the `Database` are closed by the writer thread, not just the
connection - see `writer.md`, where the reason that matters is spelled out.

## reset

Close, delete the database, reopen - the direct replacement for
`clear_site()`.

The on-disk database is a **directory**, not a single file, confirmed against
the real engine rather than assumed, so the delete branches on
`os.path.isdir`. A no-op for the in-memory case: there is nothing on disk, and
a fresh `lb.Database("")` starts empty anyway.

Why delete rather than `DELETE` per table: 21 `DELETE`s in dependency order is
both slower and easy to get wrong as the schema grows, and it leaves the file
the size it was. `PragmaConfig.fresh` exists to reclaim that.

## _build_disk_store

`graph_store: ladybug`. Takes `directory` from
`graph_stores.ladybug.directory` in config, defaulting to `data/sites`, and
ignores anything else the config block carries.

## _build_memory_store

`graph_store: memory`. Always in-memory, **regardless of any `directory` the
config happens to carry for this name**: "memory" means ephemeral, not "on
disk with a default path", and honouring a stray directory here would
silently persist a run that asked not to be persisted.
