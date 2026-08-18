"""Full-text search over the graph's own prose columns - storage-
migration plan step 9. `_LadybugSearchMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

Best-effort by design: `INSTALL FTS` needs network access on a host that
has never loaded the extension before (the storage-migration plan's own
risk callout), so nothing else in this package depends on an index
existing - `search_text()` degrades to `[]`, not an error, when
`ensure_search_indexes()` was never called or never finished.

Details: docs/dev/database/ladybug/search.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

# One full-text index per (node table, text column) the storage-migration
# plan names - Page.description, Component.text, TextContent.text,
# ComponentFamily.purpose. Rule.statement (the fifth column the plan
# lists) is the semantic layer's own, not built until that node table
# exists (storage-migration plan step 10).
_FTS_TARGETS = (
    ("Page", "page_description_fts", "description"),
    ("Component", "component_text_fts", "text"),
    ("TextContent", "text_content_fts", "text"),
    ("ComponentFamily", "component_family_purpose_fts", "purpose"),
)


class _LadybugSearchMixin:
    """Details: docs/dev/database/ladybug/search.md#_ladybugsearchmixin"""

    def ensure_search_indexes(self) -> None:
        """Best-effort: create the four FTS indexes `_FTS_TARGETS` names,
        skipping any that already exist. Never raises for "already
        exists" (confirmed against the real engine: re-creating an
        existing index raises a `RuntimeError` naming it, not a no-op) -
        a resumed crawl calling this again must not fail on its own
        earlier work. Does raise for a genuine failure (e.g. `INSTALL
        FTS` unable to reach the network on a first-ever run on an
        offline host) - per the storage-migration plan's own risk
        callout, callers that need search indexes deferred rather than
        the whole run failing should catch and log, not swallow silently
        here.
        Details: docs/dev/database/ladybug/search.md#ensure_search_indexes
        """
        def op(conn) -> None:
            conn.execute("INSTALL FTS")
            conn.execute("LOAD FTS")
            for table, index_name, column in _FTS_TARGETS:
                try:
                    conn.execute(f'CALL CREATE_FTS_INDEX("{table}", "{index_name}", ["{column}"])')
                except RuntimeError as exc:
                    if "already exists" not in str(exc):
                        raise

        self._call(op)

    def search_text(self, table: str, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Full-text search one of `_FTS_TARGETS`' indexed tables -
        `table` must be one of `"Page"`/`"Component"`/`"TextContent"`/
        `"ComponentFamily"`. Returns `[]` (not an error) if
        `ensure_search_indexes()` was never called for this store, since
        that is a normal "search not set up yet" state on an offline
        host, not a caller mistake.
        Details: docs/dev/database/ladybug/search.md#search_text
        """
        target = next((t for t in _FTS_TARGETS if t[0] == table), None)
        if target is None:
            raise ValueError(f"no FTS index defined for table {table!r}")
        _, index_name, column = target

        def op(conn) -> List[Dict[str, Any]]:
            try:
                rows = conn.execute(
                    f'CALL QUERY_FTS_INDEX("{table}", "{index_name}", $query_text) '
                    f"RETURN node.{column}, score ORDER BY score DESC LIMIT {int(limit)}",
                    {"query_text": query_text},
                )
            except RuntimeError as exc:
                # Confirmed against the real engine: "Table Page doesn't
                # have an index with name ..." - the exact, only-ever-seen
                # shape for "ensure_search_indexes() was never called".
                if "doesn't have an index" in str(exc):
                    return []
                raise
            return [{"text": text, "score": score} for text, score in rows]

        return self._call(op)
