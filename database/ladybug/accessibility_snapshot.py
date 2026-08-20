"""Per-page ARIA snapshot + CDP AXTree write/read path, docs/adr/0003.
`_LadybugAccessibilitySnapshotMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Stored directly on the existing `Page` node, not the schema's separate
`Screen` table: `Screen` is the dormant, `SERIAL`-keyed semantic-layer
node (`name`/`route_pattern`/`purpose`) a future heuristic/LLM-derived
ticket owns, and ADR-0003's `SCR-<hash>` screen id is a different,
mechanical concept computed at read time from `Page.url` (already the
route-shaped canonical key every stored `Page` carries) - reusing
`Screen`'s table would mean changing its primary-key type for a concept
that isn't the one it was reserved for.

One snapshot per page in v1 (ADR-0003's snapshot policy), so this is a
straight `SET` on the `Page` node, the same shape `title`/`description`
already take - no new node type, no history kept.

Details: docs/dev/database/ladybug/accessibility_snapshot.md#module
"""
from __future__ import annotations

from typing import Any, Dict


class _LadybugAccessibilitySnapshotMixin:
    """Details: docs/dev/database/ladybug/accessibility_snapshot.md#_ladybugaccessibilitysnapshotmixin"""

    def record_accessibility_snapshot(self, page_url: str, aria_snapshot_yaml: str, axtree_json: str) -> None:
        """Store one page's captured ARIA snapshot YAML and AXTree JSON, both
        already-serialized strings from `spiders/content/accessibility_snapshot.py`
        - this method's job is persistence, not capture or parsing.

        The `Page` is `MERGE`d, not `MATCH`ed - `containment.py`'s reasoning
        applies the same way it does to `record_state_styles`: a page whose
        `upsert_page` write has not landed yet must not silently drop this.
        Details: docs/dev/database/ladybug/accessibility_snapshot.md#record_accessibility_snapshot
        """
        if not aria_snapshot_yaml and not axtree_json:
            return

        def op(conn) -> None:
            conn.execute(
                """
                MERGE (p:Page {url: $page_url})
                SET p.aria_snapshot_yaml = $aria_snapshot_yaml, p.axtree_json = $axtree_json
                """,
                {"page_url": page_url, "aria_snapshot_yaml": aria_snapshot_yaml, "axtree_json": axtree_json},
            )

        self._call(op)

    def get_accessibility_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """`{page_url: {"aria_snapshot_yaml", "axtree_json"}}` for every page
        that has one - a page discovered before this instrumentation existed,
        or one whose capture failed, is simply absent, not present with
        blank strings.
        Details: docs/dev/database/ladybug/accessibility_snapshot.md#get_accessibility_snapshots
        """
        def op(conn) -> Dict[str, Dict[str, Any]]:
            rows = conn.execute(
                "MATCH (p:Page) WHERE p.aria_snapshot_yaml <> '' "
                "RETURN p.url, p.aria_snapshot_yaml, p.axtree_json"
            )
            return {
                url: {"aria_snapshot_yaml": aria_snapshot_yaml, "axtree_json": axtree_json}
                for url, aria_snapshot_yaml, axtree_json in rows
            }

        return self._call(op)
