"""Option/HAS_OPTION write+read path for `LadybugGraphStore` - storage-
migration plan step 8, the last JSON blob (`components.options`) retired
into real nodes. `_LadybugOptionsMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

`record_component_options` receives one of three shapes, all keyed off
which fields are present (the same detection `generators/
component_classifier.py::describe_options` already uses on the read
side, mirrored here for the write side rather than shared - the write
side works from live discovery dicts, the read side from a graph query
result, and forcing them through one JSON-shaped intermediate was
exactly the blob this step exists to delete):

- **stepper** (`increment_path`/`decrement_path` present): not really a
  list of choices at all - a compound control's own sub-element wiring.
  `Option`'s schema (`path`/`text`/`selected`/`group_name`) has no field
  for that, so a stepper is encoded as up to four `Option` rows under
  `group_name="stepper"`, each `text` a role tag (`"container"`/
  `"increment"`/`"decrement"`/`"value:<current_value>"`) rather than
  real display text - the one place in this module `text` is a
  discriminator, not prose, and `describe_options_from_rows` (the
  matching read-side reconstruction) is the only code that is allowed
  to know that convention.
- **choice_group** (`group`/`options` present): one `Option` per member,
  each carrying its own `path` - a radio/checkbox set or a dropdown's
  menu items.
- **revealed_options** (`trigger`/`revealed_options` present): one
  `Option` per revealed item, `path` always `""` - these never had a DOM
  selector of their own before consolidation either.

Details: docs/dev/database/ladybug/options.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .ids import component_id


def _option_rows_and_group(options: Dict[str, Any]) -> Optional[Tuple[List[Dict[str, Any]], str]]:
    """`(rows, group_name)` for whichever of the three shapes `options`
    is, or `None` for anything else - the same defensive "not a
    recognized shape" fallback `describe_options` uses.
    Details: docs/dev/database/ladybug/options.md#_option_rows_and_group
    """
    if "increment_path" in options and "decrement_path" in options:
        rows = []
        container = options.get("container")
        if container:
            rows.append({"path": container, "text": "container", "selected": False})
        increment_path = options.get("increment_path")
        if increment_path:
            rows.append({"path": increment_path, "text": "increment", "selected": False})
        decrement_path = options.get("decrement_path")
        if decrement_path:
            rows.append({"path": decrement_path, "text": "decrement", "selected": False})
        value_path = options.get("value_path")
        if value_path:
            rows.append({"path": value_path, "text": f"value:{options.get('current_value') or ''}", "selected": False})
        return rows, "stepper"
    if "group" in options and "options" in options:
        rows = [
            {"path": o.get("path") or "", "text": o.get("text") or "", "selected": bool(o.get("selected"))}
            for o in options.get("options") or []
        ]
        return rows, options.get("group") or ""
    if "trigger" in options and "revealed_options" in options:
        rows = [
            {"path": "", "text": o.get("text") or "", "selected": bool(o.get("selected"))}
            for o in options.get("revealed_options") or []
        ]
        return rows, options.get("trigger") or ""
    return None


class _LadybugOptionsMixin:
    """Details: docs/dev/database/ladybug/options.md#_ladybugoptionsmixin"""

    def record_component_options(
        self, page_url: str, path: str, options: Dict[str, Any], option_labels: Optional[List[str]] = None,
    ) -> None:
        """Replace one component's entire option set - full rebuild, not
        an incremental merge, since a stepper's `current_value` and a
        revealed-dropdown's member set both change across rediscovery
        passes and neither has a stable per-option key to merge on.
        `option_labels` (the pre-rendered display strings `GraphStoreSink`
        already computes via `format_option_choices`) is accepted for
        interface parity but not stored - every one of its callers reads
        `format_option_choices(get_component_ledger()[...]["options"])`
        for that same string when it actually needs it, computed fresh
        from the real `Option` rows rather than a second copy of it.
        Details: docs/dev/database/ladybug/options.md#record_component_options
        """
        parsed = _option_rows_and_group(options)
        target_id = component_id(page_url, path)

        def op(conn) -> None:
            conn.execute(
                "MATCH (:Component {id: $id})-[:HAS_OPTION]->(o:Option) DETACH DELETE o",
                {"id": target_id},
            )
            if not parsed or not parsed[0]:
                return
            rows, group_name = parsed
            for seq, row in enumerate(rows):
                row["seq"] = seq
            # MERGE, not MATCH: this can run before record_component(s)
            # ever creates the owning node - _record_choice_group writes
            # a representative's options before the batched
            # record_components call that gives it its descriptive
            # fields, same stub-then-fill pattern
            # record_component_interaction already established.
            conn.execute(
                """
                MERGE (c:Component {id: $id})
                ON CREATE SET c.path = $path
                WITH c
                UNWIND $rows AS r
                CREATE (o:Option {path: r.path, text: r.text, selected: r.selected, group_name: $group_name})
                CREATE (c)-[:HAS_OPTION {seq: r.seq}]->(o)
                """,
                {"id": target_id, "path": path, "rows": rows, "group_name": group_name},
            )

        self._call(op)
