# `database/ladybug/accessibility_snapshot.py`

## module

Per-page ARIA snapshot + CDP AXTree write/read path, docs/adr/0003.
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

## _ladybugaccessibilitysnapshotmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## record_accessibility_snapshot

Persistence only - capture and parsing live in
`spiders/content/accessibility_snapshot.py` and `generators/aria_tree.py`
respectively, neither of which this method knows about. The `Page` is
`MERGE`d, not `MATCH`ed, the same reason `record_state_styles` MERGEs its
`Component`: a page whose `upsert_page` write has not landed yet must not
silently drop this. A no-op when both fields are empty.

## get_accessibility_snapshots

`{page_url: {"aria_snapshot_yaml", "axtree_json"}}` for every page that
has one - a page discovered before this instrumentation existed, or one
whose capture failed, is absent, not present with blank strings. What
`generators/aria_tree.py::build_aria_tree` iterates to build
`tree.aria.yaml`/`tree.axtree.json`.
