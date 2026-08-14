"""Shared Cypher-fragment helpers used across Neo4jGraphStore's split
files (`neo4j_graph_store.py` for Page/Site/edges,
`neo4j_component_store.py`, `neo4j_component_family_store.py`,
`neo4j_text_content_store.py`) - kept in one place so none of those
files need to depend on each other just to share a fragment.
Details: docs/dev/database/neo4j_graph_store.md#module
"""
from __future__ import annotations

from typing import Any, Tuple

from core.interfaces import ComponentFacts

# ComponentFacts field names, in a fixed order - the single place the
# Cypher RETURN/SET fragments below and the Python-side result dicts both
# derive their field list from, so the two can't drift apart.
_FACTS_FIELDS: Tuple[str, ...] = tuple(ComponentFacts.__dataclass_fields__.keys())

# Excludes the noisy cursor:pointer catch-all layer from component counts.
_SEMANTIC_ONLY_CLAUSE = " WHERE c.layer <> 'pointer'"


def _page_ensure_clause(var: str, url_param: str) -> str:
    """MERGE a Page node keyed by (site, url_param), defaulting unset fields.
    Details: docs/dev/database/neo4j_graph_store.md#_page_ensure_clause
    """
    return (
        f"MERGE ({var}:Page {{site: $site, url: ${url_param}}}) "
        f"ON CREATE SET {var}.status = 'Pending', {var}.components = 0, "
        f"{var}.context = '-', {var}.label = '-', {var}.caption = ${url_param}"
    )


def _page_ensure_clause_from_row(var: str, row_field: str) -> str:
    """Same as `_page_ensure_clause`, keyed off an UNWIND `row` field instead
    of a top-level query param - for batched writes where each row names a
    different page (e.g. record_links' distinct link targets).
    Details: docs/dev/database/neo4j_graph_store.md#_page_ensure_clause_from_row
    """
    return (
        f"MERGE ({var}:Page {{site: $site, url: row.{row_field}}}) "
        f"ON CREATE SET {var}.status = 'Pending', {var}.components = 0, "
        f"{var}.context = '-', {var}.label = '-', {var}.caption = row.{row_field}"
    )


def _blank_cypher_literal(default: Any) -> str:
    """`false` for a bool-typed ComponentFacts field, `''` for a str-typed one."""
    return "false" if isinstance(default, bool) else "''"


# Blank default for every ComponentFacts field, Cypher-literal form - shared
# by _COMPONENT_BLANK_STUB (ghost nodes) below.
_BLANK_FACTS_ASSIGNMENTS = ", ".join(
    f"c.{f.name} = {_blank_cypher_literal(f.default)}"
    for f in ComponentFacts.__dataclass_fields__.values()
)

# ON CREATE stub for a Component reached only via an auto-create path.
# Details: docs/dev/database/neo4j_graph_store.md#_component_blank_stub
_COMPONENT_BLANK_STUB = (
    "ON CREATE SET "
    "c.tag = '', c.text = '', c.role = '', c.input_type = '', "
    "c.visible = true, c.layer = 'semantic', c.component_type = '', c.options = '', "
    "c.option_labels = [], c.caption = '', "
    "c.interacted = false, c.interaction_count = 0, c.network_requests = [], "
    f"{_BLANK_FACTS_ASSIGNMENTS}"
)

# Reads a Component's interactions back off its :INTERACTED relationships,
# in the order they happened, as the same dicts the old JSON-array property
# held. Details: docs/dev/database/neo4j_component_store.md#interacted
_INTERACTIONS_COLLECT = (
    "OPTIONAL MATCH (c)-[i:INTERACTED]->(:Page) "
    "WITH c, i ORDER BY i.seq "
    "WITH c, [x IN collect(i) | {"
    "action: x.action, value: x.value, "
    "resulting_url: x.resulting_url, source_path: x.source_path, "
    "visit_id: coalesce(x.visit_id, ''), step_seq: coalesce(x.step_seq, 0)"
    "}] AS interactions"
)

def _display_name_clause(prefix: str) -> str:
    """Cypher for a Component's short `caption`: its visible text, else
    its role, else its tag. Exists so Neo4j Browser shows "Comprar"
    instead of "div > form > button:nth-of-type(2)" - the CSS path is both
    the longest and the least readable property a caption could land on.

    Called `caption`, not `name`, because `name` is already taken twice
    over in this graph: `ComponentFacts.name` is the DOM `name` attribute
    (persisted as `c.name`, and it silently overwrote an earlier attempt
    at this) and `:Site` is keyed by `name`. `caption` collides with
    nothing and says what it is for.

    Args:
        prefix: `"$"` for a query built on top-level params (yielding
            `$text`), or `"row."` for one built inside an UNWIND (yielding
            `row.text`) - the same two forms every other fragment in this
            file comes in.
    Details: docs/dev/database/neo4j_component_store.md#caption
    """
    return (
        f"c.caption = CASE WHEN {prefix}text <> '' THEN left({prefix}text, 40) "
        f"WHEN {prefix}component_type <> '' THEN {prefix}component_type "
        f"ELSE {prefix}tag END"
    )


# Property assignments shared verbatim between record_component's ON CREATE
# and ON MATCH branches - a rediscovery always refreshes every descriptive/
# style fact the same way, unlike the interaction-ledger fields ON CREATE
# alone bootstraps (see record_component below).
_COMPONENT_DESCRIPTIVE_SET = (
    "c.tag = $tag, c.text = $text, c.role = $role, c.input_type = $input_type, "
    "c.visible = $visible, c.layer = $layer, "
    "c.x = $x, c.y = $y, c.width = $width, c.height = $height, "
    "c.component_type = $component_type, "
    + _display_name_clause("$") + ", "
    + ", ".join(f"c.{name} = ${name}" for name in _FACTS_FIELDS)
)

# Same assignments as _COMPONENT_DESCRIPTIVE_SET, reading from an UNWIND
# `row` instead of top-level query params - shared by record_components'
# ON CREATE/ON MATCH branches. Details: docs/dev/database/neo4j_graph_store.md#record_components
_COMPONENT_DESCRIPTIVE_SET_FROM_ROW = (
    "c.tag = row.tag, c.text = row.text, c.role = row.role, c.input_type = row.input_type, "
    "c.visible = row.visible, c.layer = row.layer, "
    "c.x = row.x, c.y = row.y, c.width = row.width, c.height = row.height, "
    "c.component_type = row.component_type, "
    + _display_name_clause("row.") + ", "
    + ", ".join(f"c.{name} = row.{name}" for name in _FACTS_FIELDS)
)

# `c.<name> AS <name>` for every ComponentFacts field - shared by
# get_component_states/get_component_ledger's RETURN clauses below.
_COMPONENT_FACTS_RETURN = ", ".join(f"c.{name} AS {name}" for name in _FACTS_FIELDS)
