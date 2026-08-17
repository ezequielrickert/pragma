"""Component/Interaction write path for `LadybugGraphStore` - split from
`page.py`/`text_content.py` for the same file-size reason the retired
DuckDB backend split `_duckdb_component_store.py` out on its own.
`_LadybugComponentMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)`/
`self._ensure_page(...)` (defined on `page.py`'s mixin, resolved through
`LadybugGraphStore`'s MRO) existing on whatever it ends up mixed into.

Storage-migration plan step 4. `get_component_states` does not yet carry
`options`/`network_requests` - steps 7-8 add the `Option`/`Request` nodes
those come from; the crawl's own live tracking (`GraphStoreInteractionTracker`)
only ever reads `interacted` from this method today.

Details: docs/dev/database/ladybug/component.md#module
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import ComponentFacts, VisitStep
from utils.urls import route_shape
from ._cypher import set_clause
from .schema import DESCRIPTIVE_COMPONENT_FIELDS

_SET_CLAUSE = set_clause("c", DESCRIPTIVE_COMPONENT_FIELDS)
_SET_CLAUSE_UNWIND = set_clause("c", DESCRIPTIVE_COMPONENT_FIELDS, row_alias="r.")


def _component_params(page_url: str, path: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Shared by `record_component`/`record_components`: the descriptive
    param set one component write needs, `ComponentFacts` flattened in -
    `item` is either the kwargs `record_component` was called with, or one
    entry of `record_components`' batch list, both already dict-shaped.
    Details: docs/dev/database/ladybug/component.md#_component_params
    """
    facts = item.get("facts") or ComponentFacts()
    return {
        "id": f"{page_url}|{path}", "path": path,
        "tag": item.get("tag", ""), "text": item.get("text", ""),
        "role": item.get("role", ""), "input_type": item.get("input_type", ""),
        "visible": item.get("visible", True), "layer": item.get("layer", "semantic"),
        "x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height"),
        "component_type": item.get("component_type", ""),
        **asdict(facts),
    }


class _LadybugComponentMixin:
    """Details: docs/dev/database/ladybug/component.md#_ladybugcomponentmixin"""

    def record_component(
        self,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        role: str = "",
        input_type: str = "",
        visible: bool = True,
        layer: str = "semantic",
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
        component_type: str = "",
        facts: Optional[ComponentFacts] = None,
    ) -> None:
        """Create or refresh a Component node's descriptive fields only -
        `interacted`/`interaction_count` are untouched by a rediscovery,
        bootstrapped only by the schema's own `DEFAULT` on first creation.
        Details: docs/dev/database/ladybug/component.md#record_component
        """
        item = {
            "tag": tag, "text": text, "role": role, "input_type": input_type,
            "visible": visible, "layer": layer, "x": x, "y": y, "width": width, "height": height,
            "component_type": component_type, "facts": facts,
        }
        params = _component_params(page_url, path, item)

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            conn.execute(
                f"""
                MERGE (c:Component {{id: $id}})
                ON CREATE SET c.path = $path, {_SET_CLAUSE}
                ON MATCH SET {_SET_CLAUSE}
                WITH c
                MATCH (p:Page {{url: $page_url}})
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                {**params, "page_url": page_url},
            )

        self._call(op)

    def record_components(self, page_url: str, components: List[Dict[str, Any]]) -> None:
        """Batched `record_component`: one `UNWIND` for a whole discovery
        pass's components instead of one round-trip each - collapses the
        100-300+ individual writes a component-heavy real page produces,
        same motivation as the retired DuckDB backend's `executemany`
        version.
        Details: docs/dev/database/ladybug/component.md#record_components
        """
        if not components:
            return
        rows = [_component_params(page_url, item["path"], item) for item in components]

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            # Page matched before UNWIND, not after via WITH - a MATCH
            # following a WITH that itself follows an UNWIND raised "Cannot
            # evaluate expression with type VARIABLE" against the real
            # engine (confirmed live; the single-item, non-UNWIND version
            # of this same WITH shape works fine).
            conn.execute(
                f"""
                MATCH (p:Page {{url: $page_url}})
                UNWIND $rows AS r
                MERGE (c:Component {{id: r.id}})
                ON CREATE SET c.path = r.path, {_SET_CLAUSE_UNWIND}
                ON MATCH SET {_SET_CLAUSE_UNWIND}
                MERGE (p)-[:HAS_COMPONENT]->(c)
                """,
                {"rows": rows, "page_url": page_url},
            )

        self._call(op)

    def record_component_interaction(
        self,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
        source_path: str = "",
        step: Optional[VisitStep] = None,
    ) -> None:
        """Mark a component as interacted with and append one interaction
        record - an `Interaction` node, `PERFORMED` from its `Component`
        and `RESULTED_IN` the page it left you on. An interaction that
        didn't navigate points back at its own page, never a dangling
        reference - same rule the retired DuckDB backend's
        `target_url = resulting_url or page_url` followed.

        `resulting_url` is `route_shape`d before it names a page here,
        even though every other caller in this codebase already shapes
        its own page keys before calling anything in this package -
        `PageVisitor.visit` is the one exception, passing `clean_url`'d
        (literal) values into this specific parameter on purpose
        (`ComponentInteraction.resulting_url` tracks literal identity for
        its own physical-navigation-detection reasons). Left unshaped, a
        route whose literal address changes every visit (a session-token
        page revisiting itself) reads as "navigated to a brand new page"
        indefinitely - confirmed live: a `Page` node with the same shape
        as an already-canonical one, keyed by its own un-shaped literal
        self. Every other page identity that reaches storage is already
        canonical; this is the one write path that has to enforce it
        itself rather than trust the caller.
        Details: docs/dev/database/ladybug/component.md#record_component_interaction
        """
        target_url = route_shape(resulting_url) if resulting_url else page_url
        component_id = f"{page_url}|{path}"
        params = {
            "page_url": page_url, "component_id": component_id, "path": path, "target_url": target_url,
            "action": action, "value": value, "source_path": source_path,
            "visit_id": step.visit_id if step else "", "step_seq": step.seq if step else 0,
        }

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            self._ensure_page(conn, target_url)
            # One statement, not a MERGE-then-CREATE pair - a component
            # discovered mid-crawl is expected to already exist here (the
            # stub path only guards against interacting with a component
            # discovery itself somehow missed), and there is no reason to
            # split an otherwise-atomic write into two round trips.
            #
            # MERGE (page)-[:HAS_COMPONENT]->(c), not just MERGE (c): a
            # component's own Page node owns the edge get_component_ledger
            # joins through, and record_component/record_components is
            # what normally creates it. Real crawls always discover a
            # component before interacting with it, so this only matters
            # for a stub - but the same completeness guarantee
            # `_ensure_component_stub` gave the retired DuckDB backend
            # (any write path produces a queryable component) has to hold
            # here too, confirmed the hard way: without this, a component
            # that only ever appears via this method is invisible to
            # get_component_ledger's page-to-component join entirely.
            conn.execute(
                """
                MATCH (page:Page {url: $page_url})
                MERGE (c:Component {id: $component_id})
                ON CREATE SET c.path = $path
                MERGE (page)-[:HAS_COMPONENT]->(c)
                WITH c
                MATCH (target:Page {url: $target_url})
                CREATE (i:Interaction {
                    action: $action, value: $value, source_path: $source_path,
                    visit_id: $visit_id, step_seq: $step_seq
                })
                CREATE (c)-[:PERFORMED]->(i)
                CREATE (i)-[:RESULTED_IN]->(target)
                SET c.interacted = true, c.interaction_count = c.interaction_count + 1
                """,
                params,
            )

        self._call(op)

    def get_component_states(self, page_url: str) -> Dict[str, Dict[str, Any]]:
        """All known components for one page, one query per page visit -
        read by `GraphStoreInteractionTracker` to decide what's already
        been interacted with.
        Details: docs/dev/database/ladybug/component.md#get_component_states
        """
        fields = ", ".join(f"c.{field}" for field in DESCRIPTIVE_COMPONENT_FIELDS)

        def op(conn) -> Dict[str, Dict[str, Any]]:
            rows = conn.execute(
                f"""
                MATCH (c:Component) WHERE c.id STARTS WITH $prefix
                RETURN c.path, c.interacted, c.interaction_count, {fields}
                """,
                {"prefix": f"{page_url}|"},
            )
            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                path, interacted, interaction_count = row[0], row[1], row[2]
                result[path] = {"interacted": interacted, "interaction_count": interaction_count}
                result[path].update(zip(DESCRIPTIVE_COMPONENT_FIELDS, row[3:]))
            return result

        return self._call(op)

    def count_unexplored_components(self, semantic_only: bool = True) -> Tuple[int, int]:
        """`(unexplored_count, total_count)` of components tracked across
        the whole site.
        Details: docs/dev/database/ladybug/component.md#count_unexplored_components
        """
        clause = "WHERE c.layer <> 'pointer'" if semantic_only else ""

        def op(conn) -> Tuple[int, int]:
            row = list(conn.execute(
                f"MATCH (c:Component) {clause} "
                "RETURN sum(CASE WHEN c.interacted THEN 0 ELSE 1 END), count(*)"
            ))[0]
            # int(), not the bare Decimal sum() returns - see page.py's
            # count_visited for why this matters.
            return (int(row[0] or 0), row[1])

        return self._call(op)

    def get_component_ledger(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Full per-component record for the whole site, `{page_url:
        {path: record}}`, each record carrying its own ordered
        `interactions` list.

        Does not yet carry `options`/`network_requests` - steps 7-8 add
        the `Option`/`Request` nodes those come from. Every consumer of
        this ledger already reads both defensively (`.get(...)`/`or []`),
        so their absence degrades to "nothing known yet," not a crash.
        Details: docs/dev/database/ladybug/component.md#get_component_ledger
        """
        fields = ", ".join(f"c.{field}" for field in DESCRIPTIVE_COMPONENT_FIELDS)

        def op(conn) -> Dict[str, Dict[str, Dict[str, Any]]]:
            component_rows = conn.execute(
                f"""
                MATCH (p:Page)-[:HAS_COMPONENT]->(c:Component)
                RETURN p.url, c.path, c.interacted, c.interaction_count, {fields}
                """
            )
            ledger: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for row in component_rows:
                page_url, path, interacted, interaction_count = row[0], row[1], row[2], row[3]
                record: Dict[str, Any] = {"interacted": interacted, "interaction_count": interaction_count}
                record.update(zip(DESCRIPTIVE_COMPONENT_FIELDS, row[4:]))
                record["interactions"] = []
                ledger.setdefault(page_url, {})[path] = record

            interaction_rows = conn.execute(
                """
                MATCH (p:Page)-[:HAS_COMPONENT]->(c:Component)-[:PERFORMED]->(i:Interaction)-[:RESULTED_IN]->(target:Page)
                RETURN p.url, c.path, i.action, i.value, target.url, i.source_path, i.visit_id, i.step_seq
                ORDER BY i.id
                """
            )
            for page_url, path, action, value, target_url, source_path, visit_id, step_seq in interaction_rows:
                page_components = ledger.get(page_url)
                if page_components is None or path not in page_components:
                    continue
                page_components[path]["interactions"].append(
                    {
                        "action": action, "value": value,
                        # "" when target_url == page_url, not the literal
                        # target - RESULTED_IN always points somewhere
                        # (record_component_interaction defaults a non-
                        # navigating interaction's target to its own page),
                        # so the empty-string-means-no-navigation contract
                        # every reader depends on (TraceStep.navigated,
                        # component_tree.py's redirect_target fallback) has
                        # to be reconstructed here, not read off verbatim.
                        "resulting_url": target_url if target_url != page_url else "",
                        "source_path": source_path, "visit_id": visit_id, "step_seq": step_seq,
                    }
                )
            return ledger

        return self._call(op)
