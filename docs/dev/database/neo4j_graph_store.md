# `database/neo4j_graph_store.py`

## module

This is the single place that knows about
`NEO4J_HOST`/`PORT`/`USER`/`PASSWORD`/`DATABASE` - no other module
should read those env vars directly, mirroring the per-provider Config
pattern used by every agent (e.g. `LocalConfig` in
`agents/local_agent.py`).

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

## _FACTS_FIELDS / _COMPONENT_DESCRIPTIVE_SET / _COMPONENT_FACTS_RETURN

`ComponentFacts.__dataclass_fields__` (`docs/dev/core/interfaces.md#ComponentFacts`)
is the single source of truth these three module-level constants derive
their field list from, added 2026-08-11 alongside the fifteen new
attribute/style properties themselves:

- `_FACTS_FIELDS`: the field names, in dataclass-declaration order - the
  one place `record_component`'s `**asdict(facts)` params, the blank-stub
  defaults, and the two read queries' Python-side result dicts all pull
  the same fifteen names from, so a typo in one spot can't silently drift
  from the other two.
- `_COMPONENT_DESCRIPTIVE_SET`: `c.<name> = $<name>` for every
  `ComponentFacts` field plus the pre-existing tag/text/role/etc. -
  shared verbatim between `record_component`'s `ON CREATE`/`ON MATCH`
  branches (see `_blank_cypher_literal`/`_BLANK_FACTS_ASSIGNMENTS` below
  for why hand-writing this list twice, as the pre-2026-08-11 version
  did for the smaller field set, is exactly the kind of divergence risk
  `_page_ensure_clause`/`_component_blank_stub` already exist to avoid
  elsewhere in this file).
- `_COMPONENT_FACTS_RETURN`: `c.<name> AS <name>` for the same fifteen -
  shared by `get_component_states`/`get_component_ledger`'s RETURN
  clauses.

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

Also blanks every `ComponentFacts` field (2026-08-11, via
`_BLANK_FACTS_ASSIGNMENTS` - `_blank_cypher_literal` picks Cypher `false`
for a bool-typed field, `''` for a str-typed one, read straight off each
`dataclasses.Field.default`) - a ghost node created through this path has
no more idea of a component's `css_class`/`color`/etc. than it does of
its tag/text, so it gets the same "blank, not absent" treatment as
every other descriptive field here.

## record_component_interaction

`source_path` (2026-08-11, default `""`) is embedded into the
interaction entry's JSON only when non-empty - `{"action", "value",
"resulting_url"}` for an ordinary interaction, `{"action", "value",
"resulting_url", "source_path"}` when `GraphStoreSink` redirected a
consolidated group member's interaction onto its representative node
(see docs/dev/spiders/orchestration/graph_sink.md#_resolve_write_path). Conditional,
not always-present-and-empty, so every interaction JSON blob written
before this field existed stays byte-identical to what this same call
would produce today.

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
`cli.py`'s `load_dotenv()` - e.g. a bare `python -c` script, or
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
site's Component queries) after every "fresh" purge. `ComponentFamily`
nodes get the same treatment for the same reason.

## apply_tag_labels

`SET c:{label}` - Cypher labels can't be bound parameters, so `label`
is baked directly into the query string per tag. Safe because every
value in `tag_labels` came from `component_family.py`'s `label_for_tag`,
which only ever returns a capitalized-identifier string or the literal
`"Component"` - never raw, untrusted input. Adds the label rather than
replacing any existing ones, so a Component keeps its base `:Component`
label alongside the new tag-specific one (`:Component:Button`, not just
`:Button`).

## record_component_families

Full rebuild every call, not an incremental merge: every existing
`ComponentFamily` node for `site` is `DETACH DELETE`d before the new set
is written. `UNWIND $member_paths` inside the same query that creates
the family node, `MATCH`ing each member by `(site, page_url, path)` -
if a member path doesn't resolve to a real Component (a caller bug, not
expected in the normal `Engine._apply_component_families` path, which
always derives `member_paths` from the same `get_component_ledger` read
that supplies every other field), the family node still gets created
but with fewer (or zero) `HAS_VARIANT` edges than intended, silently -
there is no defensive check here, since a mismatch would only ever come
from a caller that isn't the one this project ships.

## get_component_families

`WITH f, c ORDER BY c.page_url, c.path` before `collect()` - Cypher's
`collect()` has no implicit ordering guarantee, and `ComponentFamily.
member_paths` is a plain tuple compared positionally by callers/tests.
`elementId(f)` (not a property) is included in the `RETURN` specifically
to force Cypher's implicit grouping to key off the actual node identity,
not its properties - two distinct family nodes could in principle share
identical `tag`/`component_type`/`common_classes` values (two disjoint
clusters in the same bucket that happen to reduce to the same common-
classes intersection), and grouping by properties alone would silently
merge their member lists together.

## inferred-label

`:ComponentFamily`, `:RequestFamily` and `:Request` carry a second label,
`:Inferred`, marking them as the model's deductions rather than the crawl's
observations.

Two reasons, and the second is the durable one:

1. Legibility - `scripts/neo4j-browser.grass` colors `:Inferred` amber, so
   opening the graph shows at a glance which half is evidence.
2. It is the precondition for auditing a deduction. "Which of these nodes
   would a human need to review?" has to be a query, not a convention
   someone remembers. The human-in-the-loop review itself is out of scope
   for now (`research/plan-generacion-de-documentos.md` H6), but the label
   costs nothing today and the alternative is retrofitting it across four
   write paths later.

`clear_site` needs no change: every `:Inferred` node also carries its
original label, and those are already deleted by site.
