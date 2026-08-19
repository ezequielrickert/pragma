"""Semantic-tier write and read path for `LadybugGraphStore` - the tier the
schema declared and nothing wrote. `_LadybugSemanticMixin` is combined into
the public `LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

**Provenance is enforced here, not requested.** `schema.py` states that every
node in this tier "must carry at least one `DERIVED_FROM` edge back to the
observations that support it". A rule that lives only in a comment is a rule
that a future writer breaks by accident, so `record_entities` raises on an
entity or field with no `derived_from` rather than writing an unsupported
assertion into the same database the observation tier lives in. That is the
whole point of the tier split: a reader has to be able to tell a fact from a
deduction, and follow the deduction back.

`Screen`, `Flow` and `Rule` still have no writer. `Rule` stays frozen for the
reason `research/plan-generacion-de-documentos.md` Fase 7 froze it - its value
was almost entirely the human-in-the-loop review that is out of scope - and
the other two have no consumer asking for them yet.

Details: docs/dev/database/ladybug/semantic.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from core.interfaces import SemanticEntity, SemanticField
from .ids import component_id, split_component_id

# Recorded on every `DERIVED_FROM` edge this module writes, so a reader can
# tell which pass produced a node without joining anything.
_GENERATOR = "data_model.build_entities"
# Deterministic derivation from captured markup - not a model's opinion, and
# not a heuristic with a failure rate worth hedging.
_METHOD = "deterministic"
_CONFIDENCE = 1.0


class _LadybugSemanticMixin:
    """Details: docs/dev/database/ladybug/semantic.md#_ladybugsemanticmixin"""

    def record_entities(self, entities: Sequence[SemanticEntity], run_id: str = "") -> None:
        """Replace this site's `Entity`/`Field` set with `entities`.

        A full rebuild, like `record_component_families`: the derivation is a
        pure function of the component ledger, so a second run over a changed
        graph must not leave the previous run's entities behind next to the
        new ones.

        Raises:
            ValueError: if any entity, or any field of one, has an empty
                `derived_from`. See this module's docstring - the tier is
                only worth having if every node in it can be traced back,
                and enforcing that at the write is the only place the rule
                cannot be forgotten.
        Details: docs/dev/database/ladybug/semantic.md#record_entities
        """
        for entity in entities:
            if not entity.derived_from:
                raise ValueError(f"semantic entity {entity.name!r} has no derived_from")
            for field in entity.fields:
                if not field.derived_from:
                    raise ValueError(
                        f"semantic field {field.name!r} of {entity.name!r} has no derived_from"
                    )

        def op(conn) -> None:
            # Edges first: Ladybug refuses to delete a node that still has
            # relationships attached.
            for table in ("DERIVED_FROM", "HAS_FIELD", "EDITS"):
                conn.execute(f"MATCH ()-[r:{table}]->() DELETE r")
            conn.execute("MATCH (f:Field) DELETE f")
            conn.execute("MATCH (e:Entity) DELETE e")

            for entity in entities:
                conn.execute(
                    "CREATE (:Entity {name: $name, description: $description})",
                    {"name": entity.name, "description": entity.description},
                )
                self._link_provenance(conn, "Entity", entity.name, entity.derived_from, run_id)
                for field in entity.fields:
                    self._write_field(conn, entity.name, field, run_id)

        self._call(op)

    @staticmethod
    def _link_provenance(conn, label: str, name: str, sources, run_id: str) -> None:
        """One `DERIVED_FROM` edge per supporting component.

        `MERGE` on the `Component` rather than `MATCH`: a `MATCH` that
        matches nothing drops the whole pattern silently, the same trap
        `containment.py` documents, so a missing component would cost the
        provenance edge with no error - which is exactly the failure this
        module exists to prevent.
        Details: docs/dev/database/ladybug/semantic.md#_link_provenance
        """
        for page_url, path in sources:
            conn.execute(
                f"""
                MATCH (n:{label} {{name: $name}})
                MERGE (c:Component {{id: $component_id}})
                ON CREATE SET c.path = $path
                CREATE (n)-[:DERIVED_FROM {{method: $method, confidence: $confidence,
                                            run_id: $run_id, generator: $generator}}]->(c)
                """,
                {
                    "name": name, "component_id": component_id(page_url, path), "path": path,
                    "method": _METHOD, "confidence": _CONFIDENCE,
                    "run_id": run_id, "generator": _GENERATOR,
                },
            )

    def _write_field(self, conn, entity_name: str, field: SemanticField, run_id: str) -> None:
        """One `Field`, its `HAS_FIELD` edge, its `EDITS` edges and its
        provenance.

        `EDITS` and `DERIVED_FROM` point at the same components here and are
        both written anyway: they answer different questions. `EDITS` is "this
        field is edited through that control" - a structural fact a rebuild
        needs - while `DERIVED_FROM` is "this field exists in the document
        because of that control". They coincide today because the derivation
        is one-to-one; a later derivation that reads two controls to conclude
        one field would separate them.
        Details: docs/dev/database/ladybug/semantic.md#_write_field
        """
        conn.execute(
            """
            CREATE (:Field {name: $name, data_type: $data_type, required: $required,
                            validation: $validation, observed_values: $observed_values})
            """,
            {
                "name": field.name, "data_type": field.data_type, "required": field.required,
                "validation": field.validation, "observed_values": list(field.observed_values),
            },
        )
        conn.execute(
            """
            MATCH (e:Entity {name: $entity_name}), (f:Field {name: $field_name})
            CREATE (e)-[:HAS_FIELD]->(f)
            """,
            {"entity_name": entity_name, "field_name": field.name},
        )
        for page_url, path in field.derived_from:
            conn.execute(
                """
                MATCH (f:Field {name: $field_name})
                MERGE (c:Component {id: $component_id})
                ON CREATE SET c.path = $path
                CREATE (f)-[:EDITS]->(c)
                """,
                {
                    "field_name": field.name,
                    "component_id": component_id(page_url, path),
                    "path": path,
                },
            )
        self._link_provenance(conn, "Field", field.name, field.derived_from, run_id)

    def get_entities(self) -> List[SemanticEntity]:
        """Every `Entity` with its fields and provenance, ordered by name.

        Rebuilt into the same `SemanticEntity` shape `build_entities`
        produces, so a round-trip through the store compares equal - the same
        property `get_component_families` maintains for `ComponentFamily`.
        Details: docs/dev/database/ladybug/semantic.md#get_entities
        """
        def op(conn) -> List[SemanticEntity]:
            entity_rows = list(conn.execute(
                "MATCH (e:Entity) RETURN e.name, e.description ORDER BY e.name"
            ))
            field_rows = list(conn.execute(
                """
                MATCH (e:Entity)-[:HAS_FIELD]->(f:Field)
                RETURN e.name, f.name, f.data_type, f.required, f.validation, f.observed_values
                ORDER BY e.name, f.name
                """
            ))
            provenance = self._provenance_by_node(conn)

            fields_by_entity: Dict[str, List[SemanticField]] = {}
            for entity_name, name, data_type, required, validation, observed in field_rows:
                fields_by_entity.setdefault(entity_name, []).append(
                    SemanticField(
                        name=name, data_type=data_type, required=bool(required),
                        validation=validation, observed_values=tuple(observed or []),
                        derived_from=tuple(provenance.get(("Field", name), ())),
                    )
                )
            return [
                SemanticEntity(
                    name=entity_name,
                    description=description,
                    fields=tuple(fields_by_entity.get(entity_name, ())),
                    derived_from=tuple(provenance.get(("Entity", entity_name), ())),
                )
                for entity_name, description in entity_rows
            ]

        return self._call(op)

    @staticmethod
    def _provenance_by_node(conn) -> Dict[Any, List[Any]]:
        """`{(label, name): [(page_url, path)]}` for every semantic node.

        Read in one query per label rather than per node: an entity with
        twelve fields would otherwise cost thirteen round trips through the
        writer thread for data that is one `MATCH` away.
        Details: docs/dev/database/ladybug/semantic.md#_provenance_by_node
        """
        provenance: Dict[Any, List[Any]] = {}
        for label in ("Entity", "Field"):
            rows = conn.execute(
                f"""
                MATCH (n:{label})-[:DERIVED_FROM]->(c:Component)
                RETURN n.name, c.id ORDER BY n.name, c.id
                """
            )
            for name, node_id in rows:
                # `split_component_id` rather than a second hop through
                # HAS_COMPONENT: the page is already encoded in the id, and
                # this is the one function that knows how.
                provenance.setdefault((label, name), []).append(split_component_id(node_id))
        return provenance
