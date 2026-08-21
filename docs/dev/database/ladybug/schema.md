# database/ladybug/schema.py

## module

The whole schema as one string, and the single place every table and column
name in this package derives from - the role `_duckdb_schema.py` played for
the retired backend.

**Three tiers, separated because they carry different trust.**

- **observation** - what the crawl saw: `Site`, `Page`, `Component`,
  `Interaction`, `TextContent`, `Container`, `Option`, `Request`, `Payload`.
- **inferred** - deterministic clustering over observations:
  `ComponentFamily`, `Endpoint`.
- **semantic** - what the application means: `Screen`, `Entity`, `Field`,
  `Flow`, `Rule`.

Ladybug allows one label per node, so **a node's tier is its table**. There is
no marker label the way the retired Neo4j backend's `:Inferred` was, and
nothing to forget to set. What separates a fact from a deduction is instead
`DERIVED_FROM`, and `semantic.py::record_entities` raises rather than write a
node without it.

**No `site` column anywhere.** Every table belongs to one crawled site by
construction - one `.lbdb` per site, see `store.md`.

**`DDL` has to stay comment-free.** Ladybug's parser rejects `--` inside a
string handed to `execute()`, even between statements - confirmed against the
real engine, not inferred from the docs. So the per-table "why" lives in this
file's Python comments and in this document, and the DDL itself carries none.

**What is written today and what is only declared.** `Entity`/`Field` have a
writer (`semantic.py`, fed by `generators/data_model.py`). `Screen`, `Flow` and
`Rule` do not: `Rule` stays frozen for the reason
`research/plan-generacion-de-documentos.md` Fase 7 froze it, and the other two
have no consumer. Declared-and-unwritten is a deliberate state here, not an
oversight - the tables exist so the first writer does not also have to design
the shape.

### Derived-not-restated columns

`FACTS_FIELDS` and `DESCRIPTIVE_COMPONENT_FIELDS` are built from
`ComponentFacts.__dataclass_fields__` rather than typed out. The DDL, every
`INSERT` column list, and the `SET` fragment a rediscovery runs all come from
the same tuple, so they cannot drift apart - and adding a fact to the
dataclass adds the column.

`DESCRIPTIVE_COMPONENT_FIELDS` deliberately excludes the ledger fields
(`interacted`, `interaction_count`): those are bootstrapped by a `MERGE`'s `ON
CREATE` defaults and never touched again, so including them would let a
rediscovery reset a component's interaction history.

### Notes on individual tables

**`Interaction.blocked`/`blocked_reason`** record the mode-gate handler
(`spiders/browser/crawl4ai_crawler/hooks.py`) having intercepted at least
one mutating request this interaction tried to fire, in `immutable`
mode - decided by "Research Ladybug schema for blocked-mutation
recording" (issue #59), wired end-to-end by issue #62. A blocked
mutation never reaches the network, so it produces no `Request`/
`TRIGGERED` pair; these two scalars are the only trace of it. Added to
existing `.lbdb` databases by `store.py::_migrate_interaction_blocked_columns`,
since `CREATE ... IF NOT EXISTS` never adds a column to a table that
already exists.

**`Container`** stores direct containment only. The retired DuckDB backend
stored the full transitive closure - one row per (component, ancestor) pair at
every depth, 58,714 rows in the snapshot that shaped the storage plan, its
largest table by far. Ancestry beyond one hop is a `CONTAINS*` traversal.

**`Option`** is one row per member of a consolidated choice-group, dropdown or
revealed-options control. The representative `Component` covers the group;
these are the specific choices. `path` is the member's own original CSS
selector, from before consolidation folded it into the representative.

**`Request`** holds first-party calls only. A third-party host gets an
`Endpoint` with no `Request` at all - per-observation fidelity for a call this
application does not own is noise, not signal. See `network.md`.

**`Endpoint`** carries no aggregate columns. Status codes, schemas and auth
schemes are computed on read from the `Request` nodes that prove them, so
there is nothing here that can go stale between runs.

**`Payload`** is content-addressed request and response bodies. It was
CSS-only when stylesheet capture existed, and became the API body store that
`truncate_and_hash` had been hashing for all along without a table to receive
it.

**`DERIVED_FROM`** is one polymorphic edge table rather than one per (kind,
kind) pair, because "what derived this, how, and how confidently" is the same
question regardless of which two node types are on either end. Its `FROM`/`TO`
list is also a real constraint on what can be derived - there is no pair
reaching a `Request` from an `Entity`, which is why `generators/data_model.py`
derives from forms only.

**Node tables before relationship tables**, because Ladybug requires every
`FROM`/`TO` table a `REL TABLE` names to already exist.
