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
from typing import Any, Dict, List, Optional

from core.interfaces import ComponentFacts, VisitStep
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
        Details: docs/dev/database/ladybug/component.md#record_component_interaction
        """
        target_url = resulting_url or page_url
        component_id = f"{page_url}|{path}"
        params = {
            "component_id": component_id, "path": path, "target_url": target_url,
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
            conn.execute(
                """
                MERGE (c:Component {id: $component_id})
                ON CREATE SET c.path = $path
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
