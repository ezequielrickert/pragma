# `generators/architecture_calm.py`

## module

`architecture.calm.json`, `architecture.cyclonedx.json`, and
`architecture.md`, per docs/adr/0007 and docs/adr/0010 - replaces the
retired `architecture_map.py` entirely, not just its serialization.

`architecture.calm.json` (FINOS CALM 1.2) is reshaped from the same
`@graph` `generators/graph_export.py::build_export_graph` assembles - the
same call `export.json` itself made, not a second, independently-
detected structure (ADR-0010 point 4). CALM node ids reuse `export.json`'s
own node ids directly, so a CALM node is traceable back to its
`export.json` counterpart by id alone.

Betweenness/depth/bottleneck metrics are recomputed here via
`core/graph_metrics.py` rather than threaded through from
`build_export_graph` - `export.json`'s own schema (ADR-0002) has no room
for them, and nothing else needs them, so the small duplicate computation
keeps `export.json`'s consumer surface clean rather than growing it for
one downstream document.

## _calm_node

One CALM node: `unique-id`/`node-type`/`name`, plus pragma's own
`metadata.pragma` extension (ADR-0010 point 7 - CALM's own
`additionalProperties: true` plus a free-form `metadata` field, unlike
CycloneDX's `properties` array convention) when `core/graph_metrics.py`
has facts about this node. `node-type` is pragma's own vocabulary as a
literal string (`"screen"`/`"component"`/`"endpoint"`/`"module"`),
per ADR-0010 point 6 - CALM's sanctioned kinds are infra-shaped and
don't fit a scraped SPA's vocabulary at all.

## _relationship_id

A `short_hash` of the relationship's own identity-defining parts
(predicate, source, destination) rather than the raw strings
concatenated - `contiene`/`navega_a`/target-url combinations can be long
and URL-shaped; a hash keeps `unique-id` short and stable without losing
determinism.

## _composed_of_relationships

One CALM `composed-of` relationship per node with a non-empty `contiene`
(ADR-0010 point 6) - `container`/`nodes`, straight from the `@graph`
edge array already built.

## _connects_relationships

One CALM `connects` relationship per `navega_a`/`dispara`/`consume` edge
- `source`/`destination`, each a bare `{"node": "<id>"}` (CALM's
`node-interface` requires only `node`, so no per-node `interfaces` array
needs synthesizing, per ADR-0010 point 6).

## build_calm_document

Assembles the full payload: `build_export_graph`'s `@graph`, reshaped
into CALM nodes and relationships, annotated with
`core/graph_metrics.py`'s own metrics keyed by the same node ids.

## _modules_from_calm

One row per `module` node - label, member count, depth range across its
member screens - `architecture.md`'s Building Blocks section, walked back
out of `architecture.calm.json`'s own `composed-of` relationships rather
than recomputed, so the view can never disagree with the source.

## _bottlenecks_from_calm

Reads the `is_bottleneck` flag `core/graph_metrics.py` already computed,
off each node's `metadata.pragma` - `architecture.md`'s Risks section.

## _render_architecture_view

`architecture.md`, arc42-shaped (ADR-0010 point 3: context, building
blocks, deployment view, risks) - mechanically rendered from both source
documents, never hand-authored in parallel. Survives the "no duplicate
views" rule the same way ACT Rules Format or MADR do in `CONTEXT.md`'s
glossary: arc42's section structure is a standard reading convention for
architecture docs specifically, not a second copy of the same content.

## ArchitectureDocument

Three outputs: `architecture.calm.json` and `architecture.cyclonedx.json`
(both `kind="source"`, schema-validated against their own pragma-authored
structural schemas - two separate files, since CALM and CycloneDX are
independently-versioned external standards and one JSON root can't
validate against both `$schema`/`bomFormat` requirements at once,
ADR-0010 point 5), and `architecture.md` (`kind="view"`). Registered as
`"architecture"`, the same name the retired `architecture_map.py` used.
