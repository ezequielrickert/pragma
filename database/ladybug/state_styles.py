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

from ._component_lookup import resolve_component_ids, stub_component_id

# Keyed by (page_url, path, state, property): a rediscovery overwrites one
# value rather than appending a second, and a component whose hover colour
# changed between runs reports the new one with no duplicate left behind.
# Independent of `Component.id` (content-derived, page-decoupled per #134) -
# a declared style is inherently a fact about one page's rendering, and
# `page_url`/`path` are carried directly on `StateStyle` rather than decoded
# from it, so this key needs no help from that id's own shape.
_ID_SEPARATOR = "|"


def state_style_id(page_url: str, path: str, state: str, css_property: str) -> str:
    """The primary key one declared state value is stored under.
    Details: docs/dev/database/ladybug/state_styles.md#state_style_id
    """
    return _ID_SEPARATOR.join((page_url, path, state, css_property))


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
            self._ensure_page(conn, page_url)
            resolved = resolve_component_ids(conn, page_url, {row["path"] for row in rows})
            for row in rows:
                row["component_id"] = resolved.get(row["path"]) or stub_component_id(page_url, row["path"])
            conn.execute(
                """
                UNWIND $rows AS r
                MERGE (s:StateStyle {id: r.id})
                SET s.page_url = $page_url, s.path = r.path, s.state = r.state,
                    s.property = r.property, s.value = r.value
                """,
                {"rows": rows, "page_url": page_url},
            )
            conn.execute(
                """
                MATCH (page:Page {url: $page_url})
                UNWIND $rows AS r
                MERGE (c:Component {id: r.component_id})
                MERGE (page)-[e:HAS_COMPONENT {path: r.path}]->(c)
                MERGE (s:StateStyle {id: r.id})
                MERGE (c)-[:HAS_STATE_STYLE]->(s)
                """,
                {"rows": rows, "page_url": page_url},
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

        Read straight off `StateStyle` itself, **not** through
        `HAS_STATE_STYLE`/`HAS_COMPONENT` - going through either would undo
        the whole point of the write's `MERGE`: a component whose descriptive
        write has not landed has no `HAS_COMPONENT` edge, so its styles would
        be stored and then unreadable. Caught by
        `tests/test_ladybug_state_styles.py::test_a_style_for_a_component_not_yet_written_still_lands`.
        Details: docs/dev/database/ladybug/state_styles.md#get_state_styles
        """
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                MATCH (s:StateStyle)
                RETURN s.page_url, s.path, s.state, s.property, s.value
                ORDER BY s.page_url, s.path, s.state, s.property
                """
            )
            return [
                {"page_url": page_url, "path": path, "state": state, "property": css_property, "value": value}
                for page_url, path, state, css_property, value in rows
            ]

        return self._call(op)
