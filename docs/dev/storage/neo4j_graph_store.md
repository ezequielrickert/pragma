# `src/storage/neo4j_graph_store.py`

## module

This is the single place that knows about
`NEO4J_HOST`/`PORT`/`USER`/`PASSWORD`/`DATABASE` - no other module
should read those env vars directly, mirroring the per-provider Config
pattern used by every agent (e.g. `LocalConfig` in
`src/agents/local_agent.py`).

## logging-silence

The driver logs a WARNING-level "unknown relationship type/property"
notification whenever a query references `NAVIGATED_TO`/component before
any edge has ever been created (e.g. the very first `get_loop_signals`
call on a fresh site) - expected on a new site's first pages, not an
actual problem, so it's silenced rather than left to print via Python
logging's default stderr handler and read like a real error.

## _page_ensure_clause

Cypher fragment: `MERGE` a `Page` node keyed by `(site, url_param)`,
defaulting every field a bare rediscovery would otherwise leave unset
for a brand-new node (docs/explicativos/plan-almacenamiento.md Fase B -
"repeated Cypher patterns" finding: this exact block used to be
hand-copied into 7 different methods, 9 occurrences counting
`record_link`/`record_edge`'s two endpoints each - a real risk that a
future field added to a fresh Page's defaults gets updated in some
copies and missed in others).

Every write below that touches a `Component`/`TextContent`/edge whose
`Page` endpoint might not exist yet reuses this, so every call site
defaults a newly-implied `Page` the same way - not because a
`Component` write should ever be the thing that "creates" a page
(that's `GraphStoreSink.record_page_arrival`'s job in the normal case),
but because `GraphStore`'s own contract already documents several
auto-create paths (e.g. `record_component_interaction`'s own doc:
"mirrors `record_edge`'s auto-create of its endpoint Page nodes") that
this project intentionally keeps.

`var` is the Cypher variable to bind (`p`, `a`, `b`, ...); `url_param`
is the query parameter name holding that node's `url` (`page_url`,
`from_url`, `to_url`, ...) - both vary by call site, the defaulted
fields never do.

## _component_blank_stub

Shared `ON CREATE` stub for a Component node reached only through an
auto-create path (an interaction/options/network write for a `path`
that was never `record_component`-ed first) - blank descriptive fields,
since nothing here actually knows the component's real tag/text/role,
unlike `record_component` itself which always has real values to set.
Reused across `record_component_interaction`/`record_component_options`/
`record_component_network` (docs/explicativos/plan-almacenamiento.md
Fase B) - previously three near-identical copies, one of which
(`record_component_options`) omitted `c.options = ''` since it's about
to `SET` that field unconditionally right after anyway; including it
here uniformly is behavior-preserving (the unconditional `SET` always
wins as the final value regardless of whether `ON CREATE` or `ON MATCH`
just ran) and removes the one accidental point of divergence between
the three copies.

## Neo4jGraphStore

Neo4j Community Edition only supports a single user database, so
per-site isolation is done by tagging every node/edge with a `site`
property and scoping every query with it, rather than one database per
site.

## connect-no-password

Sending `auth=(user, None)` doesn't fail client-side - the driver
happily ships a malformed token and lets the *server* reject it, logging
a cryptic "Unsupported authentication token, missing key `credentials`"
WARN with no indication of why (seen repeatedly in practice: every code
path that touches `Neo4jGraphStore` without first going through
`src/cli.py`'s `load_dotenv()` - e.g. a bare `python -c` script, or
pytest collecting this module - hits this if `NEO4J_PASSWORD` is only
set in `.env` and not the shell). Failing fast here with an actionable
message is strictly better than one more silent retry against the
server.

## clear_site

`DETACH DELETE` on every Page tagged with this site removes all of its
incident relationships too (`NAVIGATED_TO`, `DISCOVERED_LINK`,
`HAS_PAGE`), regardless of which node "owns" them - no separate
relationship query needed. The Site node is deleted in the same pass
since nothing else references it once its pages are gone. Component
nodes are a separate label, so a Page-scoped `DETACH DELETE` does not
reach them - they'd otherwise survive (orphaned, still matching this
site's Component queries) after every "fresh" purge.
