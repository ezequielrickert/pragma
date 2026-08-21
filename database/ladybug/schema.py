"""DDL for `LadybugGraphStore` - the single source every table/edge name
in `store.py`, `network.py`, `semantic.py`, and `queries.py` derives from,
the same role `database/_duckdb_schema.py` played for the retired DuckDB
backend.

Three tiers, kept structurally separate because they carry different
trust: **observation** (`Site`/`Page`/`Component`/... - what the crawl
saw), **inferred** (`ComponentFamily`/`Endpoint` - deterministic
clustering over observations), and **semantic**
(`Screen`/`Entity`/`Field`/`Flow`/`Rule` - heuristic/LLM-derived). Ladybug
allows one label per node, so the tier a node belongs to is the table
itself, not a marker label the way the retired Neo4j backend's
`:Inferred` was - every inferred/semantic node's `DERIVED_FROM` edges are
what let a reader tell a fact from a guess, and trace a guess back to the
observations that support it.

Every table is scoped to one crawled site by construction (one `.lbdb`
file per site - see `store.py`), so unlike the DuckDB schema this
replaces, no table carries a `site` column and no key includes one.

Unlike `_duckdb_schema.py`, the per-table "why" lives in this docstring
and the comments below rather than inline SQL comments: Ladybug's parser
(confirmed against the real engine, not assumed from the docs) rejects
`--` inside a string handed to `execute()`, even between statements, so
`DDL` itself has to stay comment-free.

Details: docs/dev/database/ladybug/schema.md#module
"""
from __future__ import annotations

from typing import Tuple

from core.interfaces import ComponentFacts

# Same role `_duckdb_schema.py::FACTS_FIELDS` played: the single place the
# DDL and every INSERT column list derive their `ComponentFacts` field
# order from, so the two can't drift apart.
FACTS_FIELDS: Tuple[str, ...] = tuple(ComponentFacts.__dataclass_fields__.keys())

# Descriptive fields a component rediscovery always refreshes identically
# on both a first sighting and a later one - same set and same reasoning
# as the retired DuckDB backend's `DESCRIPTIVE_COLUMNS`: the ledger fields
# (`interacted`/`interaction_count`) are bootstrapped only by a MERGE's
# own `ON CREATE` schema defaults, never touched again by the `ON MATCH`
# clause a rediscovery runs. `observation.py` builds its `SET` fragment
# from this tuple so the same list can't drift between the two clauses.
DESCRIPTIVE_COMPONENT_FIELDS: Tuple[str, ...] = (
    "tag", "text", "role", "input_type", "visible", "layer",
    "x", "y", "width", "height", "component_type",
) + FACTS_FIELDS

# Every ComponentFacts column defaults exactly as blank as the retired
# DuckDB backend's DDL made it - FALSE for a bool-typed fact, '' for a
# string-typed one - so a bare component write with no facts supplied
# gets the same blank ledger this table's other defaults give it.
_FACTS_COLUMNS = ", ".join(
    f"{name} BOOLEAN DEFAULT false" if isinstance(field.default, bool)
    else f"{name} STRING DEFAULT ''"
    for name, field in ComponentFacts.__dataclass_fields__.items()
)

# Observation tier - what the crawl saw. `Component`'s trailing columns
# are `_FACTS_COLUMNS` above (the 15 `ComponentFacts` fields, flattened).
_OBSERVATION_DDL = f"""
CREATE NODE TABLE IF NOT EXISTS Site(
    name STRING PRIMARY KEY,
    root_url STRING DEFAULT '',
    first_crawled TIMESTAMP,
    last_crawled TIMESTAMP);

CREATE NODE TABLE IF NOT EXISTS Page(
    url STRING PRIMARY KEY,
    route_shape STRING DEFAULT '',
    status STRING DEFAULT 'Pending',
    title STRING DEFAULT '',
    description STRING DEFAULT '',
    caption STRING DEFAULT '',
    component_count INT64 DEFAULT 0,
    visited_at TIMESTAMP,
    aria_snapshot_yaml STRING DEFAULT '',
    axtree_json STRING DEFAULT '',
    metadata MAP(STRING, STRING),
    in_degree INT64 DEFAULT 0,
    out_degree INT64 DEFAULT 0,
    click_depth INT64,
    betweenness DOUBLE DEFAULT 0.0,
    pagerank DOUBLE DEFAULT 0.0,
    is_articulation_point BOOLEAN DEFAULT false,
    module_id INT64,
    module_label STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Component(
    id STRING PRIMARY KEY,
    path STRING DEFAULT '',
    tag STRING DEFAULT '',
    text STRING DEFAULT '',
    role STRING DEFAULT '',
    input_type STRING DEFAULT '',
    visible BOOLEAN DEFAULT true,
    layer STRING DEFAULT 'semantic',
    x DOUBLE, y DOUBLE, width DOUBLE, height DOUBLE,
    component_type STRING DEFAULT '',
    interacted BOOLEAN DEFAULT false,
    interaction_count INT64 DEFAULT 0,
    {_FACTS_COLUMNS});

CREATE NODE TABLE IF NOT EXISTS Interaction(
    id SERIAL PRIMARY KEY,
    action STRING DEFAULT '',
    value STRING DEFAULT '',
    source_path STRING DEFAULT '',
    visit_id STRING DEFAULT '',
    step_seq INT64 DEFAULT 0,
    blocked BOOLEAN DEFAULT false,
    blocked_reason STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS TextContent(
    id STRING PRIMARY KEY,
    path STRING DEFAULT '',
    tag STRING DEFAULT '',
    text STRING DEFAULT '',
    visible BOOLEAN DEFAULT true,
    x DOUBLE, y DOUBLE, width DOUBLE, height DOUBLE);

CREATE NODE TABLE IF NOT EXISTS Container(
    id STRING PRIMARY KEY,
    path STRING DEFAULT '',
    tag STRING DEFAULT '',
    role STRING DEFAULT '',
    landmark STRING DEFAULT '',
    element_id STRING DEFAULT '',
    css_class STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Option(
    id SERIAL PRIMARY KEY,
    path STRING DEFAULT '',
    text STRING DEFAULT '',
    selected BOOLEAN DEFAULT false,
    group_name STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Request(
    id SERIAL PRIMARY KEY,
    method STRING DEFAULT '',
    path STRING DEFAULT '',
    query_params STRING[],
    resource_type STRING DEFAULT '',
    status INT64,
    status_text STRING DEFAULT '',
    failed BOOLEAN DEFAULT false,
    failure_text STRING DEFAULT '',
    request_schema STRING DEFAULT '',
    response_schema STRING DEFAULT '',
    latency_ms INT64,
    media_type STRING DEFAULT '',
    auth_scheme STRING DEFAULT '',
    observed_at TIMESTAMP);

CREATE NODE TABLE IF NOT EXISTS Payload(
    hash STRING PRIMARY KEY,
    byte_length INT64 DEFAULT 0,
    content STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS StateStyle(
    id STRING PRIMARY KEY,
    state STRING DEFAULT '',
    property STRING DEFAULT '',
    value STRING DEFAULT '');
"""
# Interaction.blocked/blocked_reason: set when the mode-gate handler
# (spiders/browser/crawl4ai_crawler/hooks.py's `_route_gate`) intercepted
# at least one mutating request this interaction tried to fire, in
# `immutable` mode. A blocked mutation never reaches the network layer,
# so it produces no `Request` node and no `TRIGGERED` edge - these two
# scalar columns on `Interaction` itself carry the fact and its reason
# (the blocked method(s), e.g. `"POST"`) instead of forcing a phantom
# `Request`/`TRIGGERED` pair for a call that never happened. Decided by
# "Research Ladybug schema for blocked-mutation recording" (issue #59).
#
# Container: direct containment only, not the transitive closure the
# retired DuckDB backend's `containment` table stored (one row per
# (component, ancestor) pair at every depth, its largest table by far) -
# ancestry beyond one hop is a `CONTAINS*` traversal, not a lookup. See
# queries.py for the pattern.
#
# Option: one row per member of a consolidated choice-group/dropdown/
# revealed-options control (`_record_choice_group`'s representative
# Component covers the group; this is the specific choice). `path` is
# that member's own original CSS selector, from before consolidation
# folded it into the representative.
#
# Request: one row per *observed* first-party HTTP call - see network.py
# for the first-party/third-party split this table only ever holds the
# first half of; a third-party host (a tracker, an ads pixel) gets an
# Endpoint with no Request at all, since per-observation fidelity for a
# call this application doesn't own would be noise, not signal.
#
# Payload: request/response bodies, content-addressed - was CSS-only
# (stylesheet capture, retired along with the measurement pass); now the
# API body store `truncate_and_hash` was always hashing for but never had
# a table wired to receive.
#
# StateStyle: one declared `:hover`/`:focus` property value per control, from
# `extract_pseudo_styles.js`. Observation tier and not a measurement: the JS
# reads `document.styleSheets`, so unlike geometry these values do not depend
# on the viewport, on images loading, or on anything being hovered - which is
# why this runs in the ordinary discovery pass and needs no measurement pass.
# Keyed by (component, state, property) so a rediscovery overwrites a value
# instead of appending a second one.

# Inferred tier - deterministic clustering over observations.
_INFERRED_DDL = """
CREATE NODE TABLE IF NOT EXISTS ComponentFamily(
    id SERIAL PRIMARY KEY,
    tag STRING DEFAULT '',
    component_type STRING DEFAULT '',
    common_classes STRING[],
    purpose STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Endpoint(
    id STRING PRIMARY KEY,
    method STRING DEFAULT '',
    host STRING DEFAULT '',
    path_pattern STRING DEFAULT '',
    path_params STRING[],
    first_party BOOLEAN DEFAULT true,
    call_count INT64 DEFAULT 0);
"""
# Endpoint: one row per distinct (method, path pattern) - the contract,
# not the observation. Carries no aggregate columns (status/schema/auth
# unions): those are computed on read from this endpoint's own Request
# nodes via CALLS, so there is nothing here that can go stale between
# runs. See queries.py::endpoint_contract.

# Semantic tier - what the application means, not just what it renders.
# Every node here must carry at least one DERIVED_FROM edge back to the
# observations that support it - semantic.py::record_entities enforces that
# by raising, rather than trusting this comment. Entity/Field have a writer
# (generators/data_model.py, D14); Screen/Flow/Rule do not yet.
_SEMANTIC_DDL = """
CREATE NODE TABLE IF NOT EXISTS Screen(
    id SERIAL PRIMARY KEY,
    name STRING DEFAULT '',
    route_pattern STRING DEFAULT '',
    purpose STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Entity(
    id SERIAL PRIMARY KEY,
    name STRING DEFAULT '',
    description STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Field(
    id SERIAL PRIMARY KEY,
    name STRING DEFAULT '',
    data_type STRING DEFAULT '',
    required BOOLEAN DEFAULT false,
    validation STRING DEFAULT '',
    observed_values STRING[]);

CREATE NODE TABLE IF NOT EXISTS Flow(
    id SERIAL PRIMARY KEY,
    name STRING DEFAULT '',
    goal STRING DEFAULT '',
    step_count INT64 DEFAULT 0,
    outcome STRING DEFAULT '');

CREATE NODE TABLE IF NOT EXISTS Rule(
    id SERIAL PRIMARY KEY,
    statement STRING DEFAULT '',
    kind STRING DEFAULT '',
    confidence DOUBLE DEFAULT 0.0);
"""

_RELATIONSHIP_DDL = """
CREATE REL TABLE IF NOT EXISTS LINKS_TO(FROM Page TO Page, label STRING DEFAULT '');

CREATE REL TABLE IF NOT EXISTS NAVIGATES_TO(
    FROM Page TO Page,
    component STRING DEFAULT '',
    action STRING DEFAULT '',
    observation_count INT64 DEFAULT 1,
    first_seen_run STRING DEFAULT '',
    last_seen_run STRING DEFAULT '',
    created_at TIMESTAMP);

CREATE REL TABLE IF NOT EXISTS HAS_COMPONENT(FROM Page TO Component);
CREATE REL TABLE IF NOT EXISTS HAS_TEXT(FROM Page TO TextContent);
CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Container TO Component, FROM Container TO Container);
CREATE REL TABLE IF NOT EXISTS HAS_OPTION(FROM Component TO Option, seq INT64 DEFAULT 0);
CREATE REL TABLE IF NOT EXISTS HAS_STATE_STYLE(FROM Component TO StateStyle);
CREATE REL TABLE IF NOT EXISTS PERFORMED(FROM Component TO Interaction);
CREATE REL TABLE IF NOT EXISTS RESULTED_IN(FROM Interaction TO Page);
CREATE REL TABLE IF NOT EXISTS TRIGGERED(FROM Interaction TO Request);
CREATE REL TABLE IF NOT EXISTS LOADED(FROM Page TO Request);
CREATE REL TABLE IF NOT EXISTS HAS_BODY(FROM Request TO Payload, direction STRING DEFAULT '');
CREATE REL TABLE IF NOT EXISTS CALLS(FROM Request TO Endpoint);
CREATE REL TABLE IF NOT EXISTS VARIANT_OF(FROM Component TO ComponentFamily);

CREATE REL TABLE IF NOT EXISTS RENDERS(FROM Screen TO Page);
CREATE REL TABLE IF NOT EXISTS HAS_FIELD(FROM Entity TO Field);
CREATE REL TABLE IF NOT EXISTS EDITS(FROM Field TO Component);
CREATE REL TABLE IF NOT EXISTS EXPOSES(FROM Screen TO Endpoint);
CREATE REL TABLE IF NOT EXISTS STEP_OF(FROM Interaction TO Flow, seq INT64 DEFAULT 0);
CREATE REL TABLE IF NOT EXISTS GOVERNS(
    FROM Rule TO Entity, FROM Rule TO Field, FROM Rule TO Flow, FROM Rule TO Endpoint);

CREATE REL TABLE IF NOT EXISTS DERIVED_FROM(
    FROM Screen TO Page,
    FROM Entity TO Component,
    FROM Field TO Component,
    FROM Flow TO Interaction,
    FROM Rule TO Component,
    FROM Rule TO Interaction,
    FROM Rule TO Request,
    FROM Endpoint TO Request,
    FROM ComponentFamily TO Component,
    method STRING DEFAULT '',
    confidence DOUBLE DEFAULT 0.0,
    run_id STRING DEFAULT '',
    generator STRING DEFAULT '');
"""
# DERIVED_FROM: every inferred/semantic node's trail back to the
# observations it was derived from. One polymorphic edge table rather
# than one per (kind, kind) pair, since "what derived this, how, and how
# confidently" is the same question regardless of which two node types
# are on either end.

# Node tables before relationship tables - Ladybug requires every FROM/TO
# table a REL TABLE references to already exist.
DDL = _OBSERVATION_DDL + _INFERRED_DDL + _SEMANTIC_DDL + _RELATIONSHIP_DDL
