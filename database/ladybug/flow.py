"""`Flow` write and read path for `LadybugGraphStore` - the semantic
tier's third writer, following `screen.py::record_screens`'s pattern
(full-rebuild-per-run, `DERIVED_FROM`-provenanced, no-provenance-no-write).
`_LadybugFlowMixin` is combined into the public `LadybugGraphStore` class
via multiple inheritance and relies on `self._call(...)` existing on
whatever it ends up mixed into.

**Deletes are scoped by source label, same reasoning as `screen.py`.**
`DERIVED_FROM` is one rel table shared by every semantic-tier writer
(`schema.py` declares it `FROM Screen TO Page` and `FROM Entity/Field TO
Component` and, since this module, `FROM Flow TO Interaction`) - a
blanket delete here would erase whichever other writer ran first on this
same run. `record_flows` deletes only `Flow`-sourced `DERIVED_FROM` edges.
`STEP_OF` needs no such scoping: the schema declares it `FROM Interaction
TO Flow` only, so it has exactly one writer and a blanket delete is
unambiguous.

**A `Flow` has no natural-key property to re-`MATCH` after creation** -
unlike `Screen` (`page_url`, unique via `Page`) or `Entity`/`Field`
(`name`), two dead-end traces of equal length from the same start page
would produce an identical `name`/`goal`/`step_count`/`outcome`, so
matching a freshly created Flow back by its own properties could attach
one trace's `STEP_OF`/`DERIVED_FROM` edges to the wrong node. Each Flow's
node creation and all of its edges are written in the one Cypher
statement below instead, keeping the new node bound (`fl`) for the whole
statement rather than re-finding it.

Details: docs/dev/database/ladybug/flow.md#module
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from core.interfaces import SemanticFlow

# Recorded on every `DERIVED_FROM` edge this module writes.
_GENERATOR = "flows.build_flows"
# A Flow's steps are read straight off the Trace they were walked in, not
# a heuristic guess - see flows.py's own module docstring.
_METHOD = "deterministic"
_CONFIDENCE = 1.0


class _LadybugFlowMixin:
    """Details: docs/dev/database/ladybug/flow.md#_ladybugflowmixin"""

    def record_flows(self, flows: Sequence[SemanticFlow], run_id: str = "") -> None:
        """Replace this site's `Flow` set with `flows`.

        A full rebuild, like `record_screens`: a Flow has no stable
        identity across a rebuild that adds or removes traces, so
        patching in place isn't sound.

        Raises:
            ValueError: if any flow has no `derived_from`. Mirrors
                `record_entities`/`record_screens`'s own enforcement -
                this tier is only worth having if every node in it can be
                traced back to what it was observed from.
        Details: docs/dev/database/ladybug/flow.md#record_flows
        """
        for flow in flows:
            if not flow.derived_from:
                raise ValueError(f"semantic flow {flow.visit_id!r} has no derived_from")

        def op(conn) -> None:
            # Edges first: Ladybug refuses to delete a node that still has
            # relationships attached. DERIVED_FROM scoped by source label -
            # see this module's own docstring for why.
            conn.execute("MATCH (:Flow)-[r:DERIVED_FROM]->() DELETE r")
            conn.execute("MATCH ()-[r:STEP_OF]->() DELETE r")
            conn.execute("MATCH (fl:Flow) DELETE fl")

            for flow in flows:
                conn.execute(
                    """
                    CREATE (fl:Flow {name: $name, goal: $goal,
                                      step_count: $step_count, outcome: $outcome})
                    WITH fl
                    UNWIND $step_seqs AS step_seq
                    MATCH (i:Interaction {visit_id: $visit_id, step_seq: step_seq})
                    CREATE (i)-[:STEP_OF {seq: step_seq}]->(fl)
                    CREATE (fl)-[:DERIVED_FROM {method: $method, confidence: $confidence,
                                                 run_id: $run_id, generator: $generator}]->(i)
                    """,
                    {
                        "name": flow.name, "goal": flow.goal,
                        "step_count": flow.step_count, "outcome": flow.outcome,
                        "visit_id": flow.visit_id, "step_seqs": list(flow.derived_from),
                        "method": _METHOD, "confidence": _CONFIDENCE,
                        "run_id": run_id, "generator": _GENERATOR,
                    },
                )

        self._call(op)

    def get_flows(self) -> List[SemanticFlow]:
        """Every `Flow` with its steps, ordered by `visit_id` - the
        `visit_id` recovered from its own `STEP_OF`-linked `Interaction`
        nodes, since `Flow` stores no `visit_id` property of its own (see
        `SemanticFlow`'s own docstring for why). Grouping by `visit_id`
        alone is unambiguous: `build_flows` writes exactly one Flow per
        `Trace`/`visit_id`, so every row sharing a `visit_id` belongs to
        the same Flow and carries the same `name`/`goal`/`step_count`/
        `outcome`.

        Rebuilt into the same `SemanticFlow` shape `build_flows` produces,
        same round-trip property `get_screens` maintains for
        `SemanticScreen`.
        Details: docs/dev/database/ladybug/flow.md#get_flows
        """
        def op(conn) -> List[SemanticFlow]:
            rows = conn.execute(
                """
                MATCH (i:Interaction)-[e:STEP_OF]->(fl:Flow)
                RETURN i.visit_id, fl.name, fl.goal, fl.step_count, fl.outcome, e.seq
                ORDER BY i.visit_id, e.seq
                """
            )
            step_seqs_by_visit: Dict[str, List[int]] = {}
            flow_by_visit: Dict[str, Tuple[str, str, int, str]] = {}
            for visit_id, name, goal, step_count, outcome, seq in rows:
                step_seqs_by_visit.setdefault(visit_id, []).append(seq)
                flow_by_visit[visit_id] = (name, goal, step_count, outcome)

            return [
                SemanticFlow(
                    visit_id=visit_id, name=name, goal=goal,
                    step_count=step_count, outcome=outcome,
                    derived_from=tuple(step_seqs_by_visit[visit_id]),
                )
                for visit_id, (name, goal, step_count, outcome) in sorted(flow_by_visit.items())
            ]

        return self._call(op)
