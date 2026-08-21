"""Literal-row-merge collapse for `Component` - issue #134's "collapse is a
literal row merge, not a pointer layer" decision, made real: once the
matching pipeline (issue #139) decides several `Component` rows are the
same exact-tier reuse, this is what actually makes them one row again.

Its own file, not folded into `component.py` (already at this project's
file-size watch threshold) - a different concern from the write path
`record_component(s)` covers: that path decides a *rediscovery*'s
identity, this one decides a *matching pass*'s. `_LadybugComponentMergeMixin`
is combined into the public `LadybugGraphStore` class via multiple
inheritance and relies on `self._call(...)` existing on whatever it ends
up mixed into.

**Copy the edges, then `DETACH DELETE` the absorbed node** - not "repoint
in place", which Cypher/Kùzu has no operation for (an edge's endpoints are
immutable once created). Every edge table where `Component` is the `FROM`
or `TO` side gets its own copy step, each preserving that table's own
properties; `DETACH DELETE` at the end removes the absorbed node and every
original edge still pointing at it in one step, so ordering between the
copy steps and the delete doesn't matter - the copies already point at the
canonical row, unaffected by what happens to the absorbed one afterward.

`VARIANT_OF` is deliberately not handled here: per #135's pipeline
ordering, exact collapse always runs before family grouping, so no
`VARIANT_OF` edge can exist on an about-to-be-absorbed `Component` yet -
handling a case that's provably empty at call time would be dead code, not
defensive programming.

Details: docs/dev/database/ladybug/component_merge.md#module
"""
from __future__ import annotations

from typing import List, Tuple

# One row per (canonical_id, absorbed_id) - a merge that groups five
# absorbed ids into one canonical id becomes five pairs here, so every
# UNWIND-based copy query below runs once per merge pass, not once per
# absorbed component.
_MergePairs = List[Tuple[str, str]]


class _LadybugComponentMergeMixin:
    """Details: docs/dev/database/ladybug/component_merge.md#_ladybugcomponentmergemixin"""

    def merge_components(self, groups: List[Tuple[str, List[str]]]) -> None:
        """Collapse each `(canonical_id, [absorbed_id, ...])` group into
        one row - every edge `HAS_COMPONENT`/`CONTAINS`/`HAS_OPTION`/
        `HAS_STATE_STYLE`/`PERFORMED`/`DERIVED_FROM`/`EDITS` touching an
        absorbed id copies onto the canonical one (preserving that edge
        table's own properties), the absorbed rows are then deleted, and
        `interacted`/`interaction_count` on every canonical row is
        recomputed from its own (now-merged) `PERFORMED` edges - the
        union of what canonical and every absorbed row separately knew,
        not just whichever value happened to survive.

        A group whose `canonical_id` also appears in its own
        `absorbed_ids` (a caller bug, never expected from the matching
        pipeline itself) would delete the row it meant to keep - guarded
        against by skipping any pair where the two ids are equal.
        Details: docs/dev/database/ladybug/component_merge.md#merge_components
        """
        pairs: _MergePairs = [
            (canonical_id, absorbed_id)
            for canonical_id, absorbed_ids in groups
            for absorbed_id in absorbed_ids
            if absorbed_id != canonical_id
        ]
        if not pairs:
            return
        rows = [{"canonical_id": c, "absorbed_id": a} for c, a in pairs]
        absorbed_ids = [a for _, a in pairs]
        canonical_ids = sorted({c for c, _ in pairs})

        def op(conn) -> None:
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (p:Page)-[e:HAS_COMPONENT]->(:Component {id: r.absorbed_id})
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (p)-[ne:HAS_COMPONENT {path: e.path}]->(canonical)
                SET ne.element_id = e.element_id, ne.x = e.x, ne.y = e.y, ne.width = e.width, ne.height = e.height
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (parent:Container)-[:CONTAINS]->(:Component {id: r.absorbed_id})
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (parent)-[:CONTAINS]->(canonical)
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (:Component {id: r.absorbed_id})-[e:HAS_OPTION]->(o:Option)
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (canonical)-[ne:HAS_OPTION]->(o)
                SET ne.seq = e.seq
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (:Component {id: r.absorbed_id})-[:HAS_STATE_STYLE]->(s:StateStyle)
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (canonical)-[:HAS_STATE_STYLE]->(s)
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (:Component {id: r.absorbed_id})-[:PERFORMED]->(i:Interaction)
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (canonical)-[:PERFORMED]->(i)
                """,
                {"rows": rows},
            )
            # DERIVED_FROM is polymorphic (Entity/Field/Rule -> Component,
            # among the other node-type pairs it also connects) - Kùzu
            # can't create a rel bound by an unlabeled node when the table
            # spans multiple FROM types ("bound by multiple node labels"),
            # so each source label needs its own copy query.
            for source_label in ("Entity", "Field", "Rule"):
                conn.execute(
                    f"""
                    UNWIND $rows AS r
                    MATCH (source:{source_label})-[e:DERIVED_FROM]->(:Component {{id: r.absorbed_id}})
                    MATCH (canonical:Component {{id: r.canonical_id}})
                    MERGE (source)-[ne:DERIVED_FROM]->(canonical)
                    SET ne.method = e.method, ne.confidence = e.confidence, ne.run_id = e.run_id, ne.generator = e.generator
                    """,
                    {"rows": rows},
                )
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (f:Field)-[:EDITS]->(:Component {id: r.absorbed_id})
                MATCH (canonical:Component {id: r.canonical_id})
                MERGE (f)-[:EDITS]->(canonical)
                """,
                {"rows": rows},
            )
            conn.execute(
                "UNWIND $ids AS id MATCH (c:Component {id: id}) DETACH DELETE c",
                {"ids": absorbed_ids},
            )
            conn.execute(
                """
                UNWIND $ids AS id
                MATCH (c:Component {id: id})
                OPTIONAL MATCH (c)-[:PERFORMED]->(i:Interaction)
                WITH c, count(i) AS n
                SET c.interaction_count = n, c.interacted = n > 0
                """,
                {"ids": canonical_ids},
            )

        self._call(op)
