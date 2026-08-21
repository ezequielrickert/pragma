# `generators/graph_export.py`

## module

`export.json`: a JSON-LD snapshot of the crawl's live graph, per
docs/adr/0002 (ticket #97) - replaces this module's original flat JSON
dump entirely, not just its serialization. `Pantalla`/`Componente`/
`Endpoint` nodes populated from real graph-store queries, connected by
`contiene`/`navega_a`/`dispara`/`consume`/`usa_token` edges (the last
since ticket #126); `Escenario`/`Hallazgo`/`Flujo`/`Estado` stay
reserved - present in `schemas/export.schema.json`'s `type` enum,
absent from `@graph` until their own document's ticket populates them.
`Modulo`/`Entidad`/`Requisito`/`Token` are populated too - see each
node-builder's own section below for which ticket did it.

Kùzu remains the query engine; this is a portable, git-diffable export
for downstream interop (`usability`'s EARL findings cite this vocabulary
by node id), not a second queryable store.

Same "reads only from `GraphStore`, writes nothing back" shape as every
other generator here - pure, deterministic, no AI/LLM call anywhere in
this module.

## _componente_node_id

This module's own `Componente` node key - `(page, path)`, one per ledger
entry. Not `database/ladybug`'s `Component.id` (content-derived and
page-decoupled since #134, an internal storage detail this document
doesn't otherwise depend on) - inlined here rather than imported once that
function stopped having this shape.

## _pantalla_nodes

One `Pantalla` per crawled page, keyed by url. `External` pages (a link
this crawl only discovered, never visited -
`database/ladybug/page.py::count_visited` excludes them the same way)
get no node: not a screen of the audited application.

## _componente_nodes

One `Componente` per `(page, path)` the component ledger already groups
by - `database/ladybug/ids.py::component_id` keys it the same way every
other component-scoped write/read in this codebase does.

## _walk_token_groups

Recurses `tokens.json`'s `core`/`semantic` tree into `Token` nodes, keyed
by dot-joined path (`core.color.text-1`) - a token's own position in the
tree is already a short, stable, human-legible identity, unlike a
`Page`/`Component`/`Endpoint`'s (a URL, a CSS selector, a host+path),
which need `short_hash` because their natural identity is too long to
use directly. A group is told apart from a token by whether it carries a
`$value` key.

## _token_nodes

One `Token` per DTCG token, since ticket #100 (ADR-0002 point 5,
ADR-0005). Built from the same `build_tokens_document` call `tokens.json`
itself makes - not read back from that document's file (generators don't
read each other's output, only `DocumentRequest.produced`, which only the
master document gets) - so the export and `tokens.json` always agree
within one run. The `usa_token` edge (`_populate_usa_token`, below) reuses
this exact document, since ticket #126.

## _endpoint_nodes

One `Endpoint` per distinct first-party call, keyed the same way
`database/ladybug/ids.py::endpoint_id` keys the graph's own `Endpoint`
nodes: `InferredRequest.endpoint` is already `host` plus the same
path-pattern shape that function's `path_pattern` argument takes, so
`f"{method} {endpoint}"` reconstructs the identical key without a second
lookup.

## _modulo_nodes

One `Modulo` per module `core/graph_metrics.py::compute_graph_metrics`
derived (docs/adr/0007's hybrid path-prefix/Leiden pass), each
`contiene`-ing its member `Pantalla` nodes - populates `export.json`'s
reserved `Modulo` entities (ADR-0002) since ticket #102. `root` is the
crawl's own entry screen (`route_shape`d `target` from
`request.settings`), for the depth computation `compute_graph_metrics`
also does internally, even though this function only reads its module
assignments back out.

## _entidad_nodes

One `Entidad` per `data-model.json` entity, with `depende_de` added onto
the citing `Endpoint` node - ADR-0008 point 5's own edge direction, from
the citing Endpoint to its Entidad, populating `export.json`'s reserved
`Entidad` type since ticket #103. Built from the same
`build_data_model_document` call `data-model.json` itself makes, not
read back from its file - the same "generators don't read each other's
output, only recompute from the same store" discipline `_token_nodes`/
`_modulo_nodes` already follow.

## _requisito_nodes

One `Requisito` per `requirements.json` entry, with `implementa` added
onto the citing `Pantalla`/`Endpoint` node (from `links.screens`/
`.endpoints`) and `cubre` added onto the `Requisito` itself (toward its
`links.data_entities`) - ADR-0009 point 5. `links.depends_on` stays
empty in `requirements.json` itself, so no `depende_de` edge between
`Requisito` nodes populates either - reserved, not invented. A screen
citation (`SCR-<hash>`) is matched against `pantallas` by recomputing
`short_hash` per known page url, since `pantallas` is keyed by the raw
url, not the hash. Built from the same `build_requirements_document`
call `requirements.json` itself makes.

## _populate_contiene

Pantalla `contiene` Componente - one edge per pair the component ledger
already groups by, so this needs no query of its own.

## _populate_navega_a

Componente `navega_a` Pantalla when a specific component caused the
navigation (`get_edges`' own `component` field); Pantalla `navega_a`
Pantalla directly when it didn't - a whole-page redirect isn't
attributable to one element. Never emitted toward a page absent from
`@graph` (an `External` target): a dangling reference into `@graph` is
worse than an edge this document is honest about not having.

## _populate_dispara_and_consume

Componente `dispara` Endpoint for every component whose interaction
triggered a call; Pantalla `consume` Endpoint for a call the page's own
load fired with no component involved - `InferredRequest`'s own
`triggered_by`/`loaded_by` split (`core/data_contracts.md`), kept apart
rather than conflated: "called when you open /orders" and "called when
you click Save" are different facts.

## _populate_usa_token

Componente `usa_token` Token, for every catalog entry with a real
`x-tokens.color` citation (ADR-0002/0005/0006 point 5, ticket #126) -
one edge per real component instance the entry groups
(`CatalogEntry.member_paths`), never once per pattern. Reuses
`custom_elements.py`'s own `color_token_alias_by_value`/`x_tokens`
directly - the same alias computation `catalog.json` itself makes, not
a second, independently-derived one. An alias's own `{...}` DTCG
wrapper is stripped to recover the bare `Token` node id.

## build_export_graph

Assembles the full `export.json` payload: populated nodes, then every
edge-population pass over them, then a stable `sort_keys`-equivalent
ordering (`(type, id)`) so two exports of an identical graph state
produce a byte-identical file. `@context` stays the schema-locked literal
`"./export.context.jsonld"` - `schemas/export.context.jsonld` in the
repo, the same non-fetchable-identifier convention every schema's own
`$id` already uses in this codebase, not a promise the file is copied
next to every generated `export.json`.

## GraphExportDocument

`DocumentGenerator` adapter. Single `kind="source"` output - ADR-0002
names no view file for this document - schema-validated against
`schemas/export.schema.json` before it's ever written to disk.
