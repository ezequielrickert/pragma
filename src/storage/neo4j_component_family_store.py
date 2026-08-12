"""Inferred component-family CRUD for `Neo4jGraphStore` - split out of
`neo4j_graph_store.py` to keep that file under this project's file-size
threshold. `_Neo4jComponentFamilyMixin` is combined into the public
`Neo4jGraphStore` class there via multiple inheritance; it is never
instantiated on its own, and every method here relies on `self._session()`
existing on whatever it ends up mixed into.

Graph shape this writes/reads (`site` scoping and Cypher params on every
query, same discipline as the rest of `Neo4jGraphStore`):

```
(:ComponentFamily {site, tag, component_type, common_classes, member_count})
    -[:HAS_VARIANT]-> (:Component {..., already exists before this runs})
```

A `ComponentFamily` node is never a duplicate of a `Component` node - it's
a new node this file creates, pointing *at* existing `Component` nodes via
`HAS_VARIANT`. See `Neo4jGraphStore.apply_tag_labels` (own file,
`neo4j_graph_store.py`) for the separate, coarser mechanism that adds a
per-tag label (`:Button`, `:Input`, ...) directly onto `Component` nodes
themselves - a different, independent piece of the same overall feature.

Details: docs/dev/storage/neo4j_component_family_store.md#module
"""
from __future__ import annotations

from typing import Dict, List

from ..core.interfaces import ComponentFamily


class _Neo4jComponentFamilyMixin:
    """Details: docs/dev/storage/neo4j_component_family_store.md#_neo4jcomponentfamilymixin"""

    def apply_tag_labels(self, site: str, tag_labels: Dict[str, str]) -> None:
        """Add a Neo4j label to every `Component` matching each `(tag,
        label)` pair in `tag_labels` - e.g. `{"button": "Button"}` finds
        every Component with `tag == "button"` and runs `SET c:Button` on
        it, so it becomes queryable/colorable as `:Component:Button`
        (the base `:Component` label is never removed, only added to).

        Args:
            site: which site's components to label.
            tag_labels: `{raw_tag: label_name}` - see
                `GraphStore.apply_tag_labels`'s own docstring for the
                full contract (who computes this dict, and why).

        Returns:
            None. One Cypher `MATCH ... SET` statement per entry in
            `tag_labels` (not batched into a single query), since each
            entry needs a different literal label baked into its own
            query string - Cypher labels can't be bound parameters the
            way property values can. Safe to bake in directly here
            because every value in `tag_labels` came from
            `component_family.label_for_tag`, which only ever returns a
            capitalized-identifier string or the literal `"Component"` -
            never raw, untrusted input.
        Details: docs/dev/storage/neo4j_graph_store.md#apply_tag_labels
        """
        with self._session() as session:
            for tag, label in tag_labels.items():
                session.run(
                    f"MATCH (c:Component {{site: $site, tag: $tag}}) SET c:{label}",
                    site=site, tag=tag,
                )

    def record_component_families(self, site: str, families: List[ComponentFamily]) -> None:
        """Replace every `ComponentFamily` node for `site` with a fresh
        set built from `families`.

        Args:
            site: which site's families to replace.
            families: the complete new set - see
                `GraphStore.record_component_families`'s docstring for
                the full contract (this is always a full rebuild, never
                an incremental merge).

        Returns:
            None. For each `ComponentFamily`: creates one new
            `:ComponentFamily` node carrying `tag`/`component_type`/
            `common_classes`/`member_count`/`purpose` as properties, then
            one `HAS_VARIANT` edge per entry in `family.member_paths` to
            the already-existing `Component` node it identifies.
            `purpose` is whatever the family already had when passed in
            (`""` unless a caller ran it through `component_family_
            narrator.narrate_family_purposes` first - this method has no
            opinion on when/whether that happened). If a `member_paths`
            entry doesn't resolve to a real `Component` (a caller bug -
            never expected from the normal `Engine._apply_component_
            families` path, which always derives `member_paths` from the
            same `get_component_ledger` read that supplies every other
            field), that one `HAS_VARIANT` edge is silently skipped
            rather than raising - the family node still gets created,
            just with fewer edges than `member_count` claims.
        """
        with self._session() as session:
            # Full rebuild, not an incremental merge - see the interface
            # doc for why cluster membership isn't kept stable across runs.
            session.run("MATCH (f:ComponentFamily {site: $site}) DETACH DELETE f", site=site)
            for family in families:
                session.run(
                    """
                    CREATE (f:ComponentFamily:Inferred {
                        site: $site, tag: $tag, component_type: $component_type,
                        common_classes: $common_classes, member_count: $member_count,
                        purpose: $purpose,
                        caption: $component_type + ' x' + toString($member_count)
                    })
                    WITH f
                    UNWIND $member_paths AS mp
                    MATCH (c:Component {site: $site, page_url: mp[0], path: mp[1]})
                    CREATE (f)-[:HAS_VARIANT]->(c)
                    """,
                    site=site, tag=family.tag, component_type=family.component_type,
                    common_classes=list(family.common_classes),
                    member_count=len(family.member_paths), purpose=family.purpose,
                    member_paths=[list(mp) for mp in family.member_paths],
                )

    def get_component_families(self, site: str) -> List[ComponentFamily]:
        """Read every `ComponentFamily` currently recorded for `site` back
        from Neo4j, reconstructing each one's `member_paths` from its
        `HAS_VARIANT` edges.

        Args:
            site: which site's families to read.

        Returns:
            A list of `ComponentFamily`, one per `:ComponentFamily` node
            for `site` that has at least one `HAS_VARIANT` edge (a family
            node with zero edges - only possible via the silent-skip
            case described in `record_component_families` - is excluded,
            since the `MATCH` this query runs requires the relationship
            to exist). Each family's `member_paths` is sorted by
            `(page_url, path)` before being collected (`WITH f, c ORDER
            BY c.page_url, c.path`, ahead of the `collect()` call) -
            Cypher's `collect()` has no ordering guarantee of its own,
            and `member_paths` is a plain tuple `component_family.
            build_component_families` also returns pre-sorted, so a
            round-trip through this method compares equal by value. The
            query groups by `elementId(f)` (not by the family's own
            properties) specifically so two distinct family nodes that
            happen to share identical `tag`/`component_type`/
            `common_classes` (two disjoint clusters in the same bucket
            that reduce to the same common-classes intersection) don't
            get their member lists silently merged together.
        """
        with self._session() as session:
            # ORDER BY before collect() - Cypher's collect() has no implicit
            # ordering guarantee of its own, and member_paths is a plain
            # tuple compared positionally by callers/tests.
            result = session.run(
                """
                MATCH (f:ComponentFamily {site: $site})-[:HAS_VARIANT]->(c:Component)
                WITH f, c ORDER BY c.page_url, c.path
                RETURN elementId(f) AS fid, f.tag AS tag, f.component_type AS component_type,
                       f.common_classes AS common_classes, f.purpose AS purpose,
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
                    purpose=r["purpose"] or "",
                )
                for r in result
            ]
