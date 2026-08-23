"""`Rule` write and read path for `LadybugGraphStore` - the semantic
tier's fourth writer, following `flow.py::record_flows`'s pattern
(full-rebuild-per-run, `DERIVED_FROM`-provenanced, no-provenance-no-write).
`_LadybugRuleMixin` is combined into the public `LadybugGraphStore` class
via multiple inheritance and relies on `self._call(...)` existing on
whatever it ends up mixed into.

**Deletes are scoped by source label for `DERIVED_FROM`, same reasoning
as `screen.py`/`flow.py`.** `DERIVED_FROM` is one rel table shared by
every semantic-tier writer - a blanket delete here would erase whichever
other writer ran first on this same run. `record_rules` deletes only
`Rule`-sourced `DERIVED_FROM` edges. `GOVERNS` needs no such scoping: the
schema declares it `FROM Rule TO ...` only (`Entity`/`Field`/`Flow`/
`Endpoint` targets, `Field` the only one populated so far), so `Rule` is
its only possible source label and a blanket delete is unambiguous.

**A `Rule` has a natural key, unlike `Flow`.** Two components can each
declare `"required"`, but one component never declares the same
constraint twice - `(source Component, statement)` is unique by
construction (a control has one `min`, one `pattern`, one `required`
flag, one declared option set), so `record_rules` writes each Rule's node
and `DERIVED_FROM` edge in one statement, then re-`MATCH`es it by that
pair to attach its `GOVERNS` edge, rather than needing `flow.py`'s single
do-everything statement.

**`GOVERNS` is best-effort, not enforced.** A Rule's `derived_from`
component reaching a `Field` via `EDITS` depends on `record_entities`
having already run over the same component set this run - true whenever
`core/engine.py` calls `_apply_rules` after `_apply_data_model`, as it
does. If no such `Field` exists (a caller running this writer in
isolation, an out-of-order run), the Rule and its `DERIVED_FROM`
provenance are still written; only the `GOVERNS` edge is silently absent,
matching this schema's own stance that `GOVERNS`'s `Entity`/`Flow`/
`Endpoint` targets stay unpopulated rather than erroring.

Details: docs/dev/database/ladybug/rule.md#module
"""
from __future__ import annotations

from typing import List, Sequence

from core.interfaces import SemanticRule
from ._component_lookup import resolve_component_ids, stub_component_id

# Recorded on every `DERIVED_FROM` edge this module writes.
_GENERATOR = "rules.build_rules"
# A Rule's statement is read straight off declared markup, not a
# heuristic guess - see rules.py's own module docstring.
_METHOD = "deterministic"
_CONFIDENCE = 1.0


class _LadybugRuleMixin:
    """Details: docs/dev/database/ladybug/rule.md#_ladybugrulemixin"""

    def record_rules(self, rules: Sequence[SemanticRule], run_id: str = "") -> None:
        """Replace this site's `Rule` set with `rules`.

        A full rebuild, like `record_screens`/`record_flows`: a Rule has
        no stable identity across a rebuild that adds, removes or
        reshapes form fields, so patching in place isn't sound.

        Raises:
            ValueError: if any rule has no `derived_from`. Mirrors
                `record_entities`/`record_screens`/`record_flows`'s own
                enforcement - this tier is only worth having if every
                node in it can be traced back to what it was observed
                from.
        Details: docs/dev/database/ladybug/rule.md#record_rules
        """
        for rule in rules:
            if not rule.derived_from:
                raise ValueError(f"semantic rule {rule.statement!r} has no derived_from")

        def op(conn) -> None:
            # Edges first: Ladybug refuses to delete a node that still has
            # relationships attached. DERIVED_FROM scoped by source label -
            # see this module's own docstring for why. GOVERNS stays
            # blanket - Rule is its only source label.
            conn.execute("MATCH (:Rule)-[r:DERIVED_FROM]->() DELETE r")
            conn.execute("MATCH ()-[r:GOVERNS]->() DELETE r")
            conn.execute("MATCH (r:Rule) DELETE r")

            for rule in rules:
                self._write_rule(conn, rule, run_id)

        self._call(op)

    def _write_rule(self, conn, rule: SemanticRule, run_id: str) -> None:
        """One `Rule` node, its `DERIVED_FROM` edge, and (best-effort) its
        `GOVERNS` edge toward the `Field` its source `Component` edits.
        Details: docs/dev/database/ladybug/rule.md#_write_rule
        """
        page_url, path = rule.derived_from
        self._ensure_page(conn, page_url)
        resolved = resolve_component_ids(conn, page_url, [path])
        component_id = resolved.get(path) or stub_component_id(page_url, path)

        conn.execute(
            """
            MATCH (page:Page {url: $page_url})
            MERGE (c:Component {id: $component_id})
            MERGE (page)-[:HAS_COMPONENT {path: $path}]->(c)
            CREATE (r:Rule {statement: $statement, kind: $kind, confidence: $rule_confidence})
            CREATE (r)-[:DERIVED_FROM {method: $method, confidence: $confidence,
                                        run_id: $run_id, generator: $generator}]->(c)
            """,
            {
                "page_url": page_url, "path": path, "component_id": component_id,
                "statement": rule.statement, "kind": rule.kind, "rule_confidence": rule.confidence,
                "method": _METHOD, "confidence": _CONFIDENCE,
                "run_id": run_id, "generator": _GENERATOR,
            },
        )
        conn.execute(
            """
            MATCH (r:Rule {statement: $statement})-[:DERIVED_FROM]->(c:Component {id: $component_id})
            MATCH (f:Field)-[:EDITS]->(c)
            CREATE (r)-[:GOVERNS]->(f)
            """,
            {"statement": rule.statement, "component_id": component_id},
        )

    def get_rules(self) -> List[SemanticRule]:
        """Every `Rule` with its source `Component`'s `(page_url, path)`,
        ordered by `(page_url, path, statement)`.

        Rebuilt into the same `SemanticRule` shape `build_rules` produces,
        same round-trip property `get_screens`/`get_flows` maintain for
        their own semantic types.
        Details: docs/dev/database/ladybug/rule.md#get_rules
        """
        def op(conn) -> List[SemanticRule]:
            rows = conn.execute(
                """
                MATCH (r:Rule)-[:DERIVED_FROM]->(c:Component)
                MATCH (page:Page)-[e:HAS_COMPONENT]->(c)
                RETURN DISTINCT r.statement, r.kind, r.confidence, page.url, e.path
                ORDER BY page.url, e.path, r.statement
                """
            )
            return [
                SemanticRule(statement=statement, kind=kind, confidence=confidence, derived_from=(page_url, path))
                for statement, kind, confidence, page_url, path in rows
            ]

        return self._call(op)
