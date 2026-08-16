"""Schema DDL and shared field lists for `DuckDBGraphStore` and its mixins.

Mirrors `_neo4j_cypher_helpers.py`'s role: one place every split file
(`duckdb_graph_store.py`, `duckdb_component_store.py`,
`duckdb_component_family_store.py`, `duckdb_request_family_store.py`,
`duckdb_text_content_store.py`) imports from, so none of them need to
depend on each other just to share a table definition or a field list.

This is Phase 3 of the storage migration plan (parity with the existing
`GraphStore` contract, running on DuckDB instead of Neo4j) - the JSON-
string fields (`options`, `network_requests`, `metadata`, `measurements`,
`accessibility_violations`) stay JSON-encoded TEXT columns here, same as
both existing backends, because the interface itself still hands them in
that shape. Phase 4 replaces the interface's JSON-string methods with
typed contracts; this file's `network_requests`/`options`/etc. columns are
exactly what Phase 4 will split into real child tables.

Details: docs/dev/database/_duckdb_schema.md#module
"""
from __future__ import annotations

from typing import Tuple

from core.interfaces import ComponentFacts

# Same role as _neo4j_cypher_helpers._FACTS_FIELDS: the single place the
# DDL, the INSERT column lists, and the Python-side result dicts all derive
# their ComponentFacts field order from, so the three can't drift apart.
FACTS_FIELDS: Tuple[str, ...] = tuple(ComponentFacts.__dataclass_fields__.keys())

# Every ComponentFacts column defaults exactly as blank as
# `_neo4j_cypher_helpers._COMPONENT_BLANK_STUB` makes it - FALSE for a
# bool-typed fact, '' for a string-typed one - so a bare
# `INSERT INTO components (site, page_url, path) VALUES (...)` (the
# auto-create path record_component_interaction/_options/_network use for
# a component never explicitly discovered) gets the same blank ledger this
# table's other defaults give it, declaratively, with no separate stub
# fragment to keep in sync.
_FACTS_COLUMNS = ", ".join(
    f"{name} BOOLEAN NOT NULL DEFAULT FALSE" if isinstance(field.default, bool)
    else f"{name} TEXT NOT NULL DEFAULT ''"
    for name, field in ComponentFacts.__dataclass_fields__.items()
)

# Descriptive fields a component rediscovery always refreshes identically on
# both a first sighting and a later one - same set as Neo4j's
# _COMPONENT_DESCRIPTIVE_SET, and for the same reason: the ledger fields
# (options/interacted/interaction_count/network_requests) are bootstrapped
# only by the INSERT's own VALUES defaults, never touched again by the
# ON CONFLICT DO UPDATE clause built from this list.
DESCRIPTIVE_COLUMNS: Tuple[str, ...] = (
    "tag", "text", "role", "input_type", "visible", "layer",
    "x", "y", "width", "height", "component_type",
) + FACTS_FIELDS

# "tag = $tag, text = $text, ..." - the ON CONFLICT DO UPDATE SET clause
# shared by record_component/record_components.
DESCRIPTIVE_UPDATE_SET = ", ".join(f"{col} = ${col}" for col in DESCRIPTIVE_COLUMNS)

DDL = f"""
CREATE TABLE IF NOT EXISTS sites (
    name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS pages (
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending',
    components INTEGER NOT NULL DEFAULT 0,
    context TEXT NOT NULL DEFAULT '-',
    label TEXT NOT NULL DEFAULT '-',
    description TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    visited_at TEXT NOT NULL DEFAULT '-',
    -- network_requests stays a JSON-TEXT blob here, unlike metadata/
    -- accessibility/measurements below: Phase 6 (full payload capture)
    -- is where network data gets its real relational treatment
    -- (requests/payloads, content-addressed) - building a partial
    -- version now would be thrown away the moment that phase lands.
    network_requests TEXT,
    PRIMARY KEY (site, url)
);

-- One row per <meta> tag, replacing pages.metadata's old JSON-blob column -
-- real columns for data that was always flat key/value pairs.
CREATE TABLE IF NOT EXISTS page_metadata (
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    meta_name TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (site, url, meta_name)
);

-- Replaces pages.accessibility_violations - one row per violated rule
-- (axe_run.js's own shape: rule_id/impact/help/help_url/criteria/
-- total_nodes), with the per-element detail broken out into its own
-- child table below instead of nested inside a JSON blob.
CREATE SEQUENCE IF NOT EXISTS violation_id_seq START 1;
CREATE TABLE IF NOT EXISTS accessibility_violations (
    violation_id BIGINT PRIMARY KEY DEFAULT nextval('violation_id_seq'),
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    rule_id TEXT NOT NULL DEFAULT '',
    impact TEXT NOT NULL DEFAULT '',
    help TEXT NOT NULL DEFAULT '',
    help_url TEXT NOT NULL DEFAULT '',
    -- Small, fixed-shape list of wcag tag strings (e.g. "wcag2a") - JSON
    -- text rather than its own child table; the per-element nodes below
    -- are the part worth real rows, not this.
    criteria TEXT NOT NULL DEFAULT '[]',
    total_nodes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS accessibility_violation_nodes (
    violation_id BIGINT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    axe_target TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT ''
);

-- Replaces pages.measurements - extract_pseudo_styles.js's per-element
-- "path, states by hover/focus, each a property/value map" shape,
-- flattened to one row per (path, state, property).
CREATE TABLE IF NOT EXISTS page_pseudo_styles (
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    path TEXT NOT NULL,
    state TEXT NOT NULL,
    property TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT ''
);

-- probe_focus.js's per-Tab-press snapshot, one row per press in order.
CREATE TABLE IF NOT EXISTS page_tab_order (
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    seq INTEGER NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    tag TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    focus_visible BOOLEAN NOT NULL DEFAULT FALSE,
    dom_index INTEGER,
    tabindex TEXT NOT NULL DEFAULT '',
    offscreen BOOLEAN NOT NULL DEFAULT FALSE
);

-- Structural containment (Storage Phase 5) - which real layout/landmark
-- containers a component sits inside, from discover_components.js's
-- `structuralAncestorsOf`. One row per (component, structural ancestor)
-- pair, nearest ancestor at depth 1 - not every DOM ancestor, only the
-- curated structural/landmark ones. This is what unblocks grouping
-- components into modules instead of only ever reading a flat list.
CREATE TABLE IF NOT EXISTS containment (
    site TEXT NOT NULL,
    page_url TEXT NOT NULL,
    child_path TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    depth INTEGER NOT NULL,
    parent_tag TEXT NOT NULL DEFAULT '',
    parent_role TEXT NOT NULL DEFAULT '',
    parent_landmark TEXT NOT NULL DEFAULT '',
    parent_id TEXT NOT NULL DEFAULT '',
    parent_class TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS links (
    site TEXT NOT NULL,
    from_url TEXT NOT NULL,
    to_url TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (site, from_url, to_url)
);

CREATE TABLE IF NOT EXISTS edges (
    site TEXT NOT NULL,
    from_url TEXT NOT NULL,
    to_url TEXT NOT NULL,
    component TEXT NOT NULL,
    action TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    first_seen_run TEXT NOT NULL DEFAULT '',
    last_seen_run TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (site, from_url, to_url, component, action)
);

CREATE TABLE IF NOT EXISTS components (
    site TEXT NOT NULL,
    page_url TEXT NOT NULL,
    path TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    input_type TEXT NOT NULL DEFAULT '',
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    layer TEXT NOT NULL DEFAULT 'semantic',
    x DOUBLE, y DOUBLE, width DOUBLE, height DOUBLE,
    component_type TEXT NOT NULL DEFAULT '',
    options TEXT NOT NULL DEFAULT '',
    option_labels TEXT NOT NULL DEFAULT '[]',
    interacted BOOLEAN NOT NULL DEFAULT FALSE,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    network_requests TEXT NOT NULL DEFAULT '[]',
    {_FACTS_COLUMNS},
    PRIMARY KEY (site, page_url, path)
);

CREATE SEQUENCE IF NOT EXISTS interaction_id_seq START 1;
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id BIGINT PRIMARY KEY DEFAULT nextval('interaction_id_seq'),
    site TEXT NOT NULL,
    page_url TEXT NOT NULL,
    path TEXT NOT NULL,
    action TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    resulting_url TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    navigated BOOLEAN NOT NULL DEFAULT FALSE,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    visit_id TEXT NOT NULL DEFAULT '',
    step_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS text_content (
    site TEXT NOT NULL,
    page_url TEXT NOT NULL,
    path TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    x DOUBLE, y DOUBLE, width DOUBLE, height DOUBLE,
    PRIMARY KEY (site, page_url, path)
);

CREATE SEQUENCE IF NOT EXISTS family_id_seq START 1;
CREATE TABLE IF NOT EXISTS component_families (
    family_id BIGINT PRIMARY KEY DEFAULT nextval('family_id_seq'),
    site TEXT NOT NULL,
    tag TEXT NOT NULL,
    component_type TEXT NOT NULL,
    common_classes TEXT NOT NULL DEFAULT '[]',
    purpose TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS component_family_members (
    family_id BIGINT NOT NULL,
    page_url TEXT NOT NULL,
    path TEXT NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS request_id_seq START 1;
CREATE TABLE IF NOT EXISTS inferred_requests (
    request_id BIGINT PRIMARY KEY DEFAULT nextval('request_id_seq'),
    site TEXT NOT NULL,
    method TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    query_params TEXT NOT NULL DEFAULT '[]',
    body_shape TEXT NOT NULL DEFAULT '',
    response_shape TEXT NOT NULL DEFAULT '',
    loaded_by TEXT NOT NULL DEFAULT '[]',
    status_codes TEXT NOT NULL DEFAULT '[]',
    latencies_ms TEXT NOT NULL DEFAULT '[]',
    auth_schemes TEXT NOT NULL DEFAULT '[]',
    media_types TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS inferred_request_triggers (
    request_id BIGINT NOT NULL,
    page_url TEXT NOT NULL,
    path TEXT NOT NULL
);
"""
