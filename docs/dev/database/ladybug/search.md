# database/ladybug/search.py

## module

Full-text search over the graph's prose columns.

**Best-effort by design.** `INSTALL FTS` needs network access on a host that
has never loaded the extension - the storage plan's own risk callout - so
nothing else in this package depends on an index existing. `search_text()`
degrades to `[]` rather than raising when `ensure_search_indexes()` was never
called or never finished.

Four indexes, one per (table, prose column): `Page.description`,
`Component.text`, `TextContent.text`, `ComponentFamily.purpose`.
`Rule.statement` is the fifth the plan names and is not built - that table has
no writer yet, and an index over an empty table would suggest otherwise.

## _ladybugsearchmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## ensure_search_indexes

Creates the four indexes, skipping any that already exist.

**"Already exists" is not an error here, and finding that out took the real
engine**: re-creating an existing index raises a `RuntimeError` naming it
rather than being a no-op, so a resumed crawl calling this again would fail on
its own earlier work. Swallowed for that case only.

A genuine failure - `INSTALL FTS` unable to reach the network on a first-ever
run on an offline host - **does** raise. Per the storage plan's risk callout,
a caller that would rather defer search than fail the run should catch and log
at the call site, where the decision belongs; swallowing it here would hide
the difference between "no index" and "no network" from every caller at once.

## search_text

Query one indexed (table, column) pair. Returns `[]` when no index exists,
which is the same answer as "nothing matched" - a caller that needs to
distinguish them has to call `ensure_search_indexes()` and handle its raise.

That conflation is deliberate: the alternative is every consumer of a
best-effort feature carrying a branch for infrastructure it did not ask about.
Stated here so it is a known limit rather than a surprise.
