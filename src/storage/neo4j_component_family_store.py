"""Inferred component-family CRUD for `Neo4jGraphStore` - split out of
`neo4j_graph_store.py` to keep that file under this project's file-size
threshold. `_Neo4jComponentFamilyMixin` is combined into the public
`Neo4jGraphStore` class there via multiple inheritance; it is never
instantiated on its own, and every method here relies on `self._session()`
existing on whatever it ends up mixed into.
Details: docs/dev/storage/neo4j_component_family_store.md#module
"""
from __future__ import annotations

from typing import Dict, List

from ..core.interfaces import ComponentFamily


class _Neo4jComponentFamilyMixin:
    """Details: docs/dev/storage/neo4j_component_family_store.md#_neo4jcomponentfamilymixin"""

    def apply_tag_labels(self, site: str, tag_labels: Dict[str, str]) -> None:
        # Cypher labels can't be bound parameters - `label` is baked into
        # the query string. Safe here because every value in `tag_labels`
        # came from `label_for_tag` (component_family.py), which only ever
        # returns a capitalized-identifier string or the literal
        # "Component" - never raw, untrusted input.
        # Details: docs/dev/storage/neo4j_graph_store.md#apply_tag_labels
        with self._session() as session:
            for tag, label in tag_labels.items():
                session.run(
                    f"MATCH (c:Component {{site: $site, tag: $tag}}) SET c:{label}",
                    site=site, tag=tag,
                )

    def record_component_families(self, site: str, families: List[ComponentFamily]) -> None:
        with self._session() as session:
            # Full rebuild, not an incremental merge - see the interface
            # doc for why cluster membership isn't kept stable across runs.
            session.run("MATCH (f:ComponentFamily {site: $site}) DETACH DELETE f", site=site)
            for family in families:
                session.run(
                    """
                    CREATE (f:ComponentFamily {
                        site: $site, tag: $tag, component_type: $component_type,
                        common_classes: $common_classes, member_count: $member_count
                    })
                    WITH f
                    UNWIND $member_paths AS mp
                    MATCH (c:Component {site: $site, page_url: mp[0], path: mp[1]})
                    CREATE (f)-[:HAS_VARIANT]->(c)
                    """,
                    site=site, tag=family.tag, component_type=family.component_type,
                    common_classes=list(family.common_classes),
                    member_count=len(family.member_paths),
                    member_paths=[list(mp) for mp in family.member_paths],
                )

    def get_component_families(self, site: str) -> List[ComponentFamily]:
        with self._session() as session:
            # ORDER BY before collect() - Cypher's collect() has no implicit
            # ordering guarantee of its own, and member_paths is a plain
            # tuple compared positionally by callers/tests.
            result = session.run(
                """
                MATCH (f:ComponentFamily {site: $site})-[:HAS_VARIANT]->(c:Component)
                WITH f, c ORDER BY c.page_url, c.path
                RETURN elementId(f) AS fid, f.tag AS tag, f.component_type AS component_type,
                       f.common_classes AS common_classes,
                       collect([c.page_url, c.path]) AS member_paths
                """,
                site=site,
            )
            return [
                ComponentFamily(
                    tag=r["tag"],
                    component_type=r["component_type"],
                    common_classes=tuple(r["common_classes"] or []),
                    member_paths=tuple(tuple(mp) for mp in r["member_paths"]),
                )
                for r in result
            ]
