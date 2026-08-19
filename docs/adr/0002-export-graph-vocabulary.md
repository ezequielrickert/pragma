# `export.json` is a JSON-LD snapshot of Kùzu, not a second graph engine

**Status**: accepted

`database/ladybug/` already runs on Kùzu, an embedded property-graph database (confirmed via its
Cypher-style queries — `MATCH (from:Page)-[e:NAVIGATES_TO]->(to:Page)`), migrated off a retired
DuckDB backend. The format audit's proposal to weigh a property-graph engine (Neo4j / Kùzu /
DuckDB+DuckPGQ) as a query layer for `export.json` is therefore moot: one already exists and is
already the thing FU-3's module-exclusion queries should run against.

Decided: `export.json` is a JSON-LD **export** of the live Kùzu graph — generated once per run for
portability, git-diffability, and interop with other JSON-LD documents (`usability`'s EARL findings
cite this vocabulary). It is not built to be independently queryable; Kùzu remains the query engine.

Following `coverage`'s reserved-field pattern (ADR-0001): the node/edge vocabulary is locked now, in
full, but only `Pantalla`, `Componente`, `Endpoint` and the edges `contiene`/`navega_a`/`dispara`/
`consume` are populated from real Kùzu queries today (`get_edges`, `get_component_ledger`,
`get_inferred_requests`). `Modulo`, `Entidad`, `Requisito`, `Escenario`, `Hallazgo`, `Token`,
`Flujo`/`Estado` and the edges `implementa`/`viola`/`deriva_de`/`depende_de`/`usa_token`/`cubre` are
reserved — present in `export.context.jsonld` and `export.schema.json`'s `type` enum, absent from
`@graph` until their source ticket (architecture #72, data-model #73, prd #74, tokens #69, usability
#75 / accessibility #76, gherkin #77, flows #78) resolves and that document's generator starts
emitting them.

`export.context.jsonld` graduates out of the map's fog now rather than waiting for the new-document
wave — an inline `@context` that later needs its own file would be a breaking change to every
`export.json` already produced. Versioned via a top-level `$version` key (`v1`), so a future
vocabulary extension doesn't retroactively invalidate old snapshots.

Not decided here: flipping `core/config.py`'s `export_json: bool = False` to `True`. Flipping it now
would default-enable the *current* flat, non-JSON-LD export.json (`generators/graph_export.py`), not
the vocabulary this ADR locks — that flip belongs to the implementation session that rewrites the
generator, not this decisions-only ticket.

Wayfinder ticket: [export: lock graph vocabulary and JSON-LD context](https://github.com/ezequielrickert/pragma/issues/66),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
