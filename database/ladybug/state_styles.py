"""`StateStyle`/`HAS_STATE_STYLE` write+read path - the declared `:hover` and
`:focus` values a control takes on. `_LadybugStateStyleMixin` is combined into
the public `LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

**Observation tier, not a measurement.** `extract_pseudo_styles.js` reads
`document.styleSheets` and matches the declared rules against elements in their
resting state, so these values depend on neither the viewport, nor images
loading, nor anything being hovered. That is what lets them come from the
ordinary discovery pass rather than from the measurement pass they were
originally written for - and it is why D10 gets its interaction states back
without that pass being revived.

Its own module rather than part of `component.py`, which is already at this
project's file-size watch threshold, and split-by-concern is the shape the rest
of this package uses.

Details: docs/dev/database/ladybug/state_styles.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

from .ids import component_id, split_component_id

# Keyed by (component, state, property): a rediscovery overwrites one value
# rather than appending a second, and a component whose hover colour changed
# between runs reports the new one with no duplicate left behind.
_ID_SEPARATOR = "|"


def state_style_id(page_url: str, path: str, state: str, css_property: str) -> str:
    """The primary key one declared state value is stored under.
    Details: docs/dev/database/ladybug/state_styles.md#state_style_id
    """
    return _ID_SEPARATOR.join((component_id(page_url, path), state, css_property))


class _LadybugStateStyleMixin:
    """Details: docs/dev/database/ladybug/state_styles.md#_ladybugstatestylemixin"""

    def record_state_styles(self, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """`entries`: one `{"path", "states"}` per control, exactly what
        `extract_pseudo_styles.js` returns and `PageState.pseudo_styles`
        carries - `states` being `{"hover": {"color": "#fff", ...}, ...}`.

        Flattened here rather than stored as the nested shape: one row per
        (state, property) is what makes "which hover colours does this site
        use" a query instead of a parse, which was the whole point of retiring
        the JSON blobs.

        The `Component` is `MERGE`d, not `MATCH`ed, for the reason
        `containment.py` documents at length: a `MATCH` that matches nothing
        drops the entire pattern silently, so a control whose descriptive write
        has not landed yet would lose its styles with no error.
        Details: docs/dev/database/ladybug/state_styles.md#record_state_styles
        """
        rows = [
            {
                "id": state_style_id(page_url, entry["path"], state, css_property),
                "component_id": component_id(page_url, entry["path"]),
                "path": entry["path"],
                "state": state,
                "property": css_property,
                "value": value,
            }
            for entry in entries
            if entry.get("path")
            for state, declarations in (entry.get("states") or {}).items()
            for css_property, value in (declarations or {}).items()
            if value
        ]
        if not rows:
            return

        def op(conn) -> None:
            conn.execute(
                """
                UNWIND $rows AS r
                MERGE (s:StateStyle {id: r.id})
                SET s.state = r.state, s.property = r.property, s.value = r.value
                """,
                {"rows": rows},
            )
            conn.execute(
                """
                UNWIND $rows AS r
                MERGE (c:Component {id: r.component_id})
                ON CREATE SET c.path = r.path
                MERGE (s:StateStyle {id: r.id})
                MERGE (c)-[:HAS_STATE_STYLE]->(s)
                """,
                {"rows": rows},
            )

        self._call(op)

    def get_state_styles(self) -> List[Dict[str, Any]]:
        """Every declared state value in the site, one dict per
        `(page_url, path, state, property, value)`, sorted.

        Flat and unaggregated on purpose. `generators/design_tokens.py` counts
        them into tokens, and that counting is a document's editorial decision -
        which properties are worth a token, how ties break - not something this
        package should have an opinion about. Same boundary
        `get_component_ledger` keeps for `options`.

        The page comes from `split_component_id`, **not** from a hop through
        `HAS_COMPONENT`. Going through the page would undo the whole point of
        the write's `MERGE`: a component whose descriptive write has not landed
        has no `HAS_COMPONENT` edge, so its styles would be stored and then
        unreadable. Caught by
        `tests/test_ladybug_state_styles.py::test_a_style_for_a_component_not_yet_written_still_lands`.
        Details: docs/dev/database/ladybug/state_styles.md#get_state_styles
        """
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                MATCH (c:Component)-[:HAS_STATE_STYLE]->(s:StateStyle)
                RETURN c.id, s.state, s.property, s.value
                ORDER BY c.id, s.state, s.property
                """
            )
            styles = []
            for component_id_value, state, css_property, value in rows:
                page_url, path = split_component_id(component_id_value)
                styles.append({
                    "page_url": page_url, "path": path,
                    "state": state, "property": css_property, "value": value,
                })
            return styles

        return self._call(op)
