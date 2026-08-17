"""Page/link/edge write path for `LadybugGraphStore` - the navigation-
graph half of the observation tier, split from `component.py`/
`text_content.py` for the same file-size reason the retired DuckDB
backend split `duckdb_graph_store.py` from its own component/text-content
mixins. `_LadybugPageMixin` is combined into the public
`LadybugGraphStore` class via multiple inheritance and relies on
`self._call(...)` existing on whatever it ends up mixed into.

`_ensure_page` lives here specifically because this is the mixin that
owns `upsert_page`'s full contract - `component.py`/`text_content.py`
call `self._ensure_page(...)`, resolved through `LadybugGraphStore`'s
MRO rather than a direct import, same pattern the retired DuckDB
backend's mixins used against `duckdb_graph_store.py::_ensure_page`.

Storage-migration plan step 4. None of `site` survives as a parameter
here, unlike every DuckDB method this replaces - see `store.py`'s own
module docstring for why.

Details: docs/dev/database/ladybug/page.md#module
"""
from __future__ import annotations

from typing import Dict, List

from .clock import now


class _LadybugPageMixin:
    """Details: docs/dev/database/ladybug/page.md#_ladybugpagemixin"""

    def _ensure_page(self, conn, url: str) -> None:
        """Create a bare Pending page if `url` doesn't exist yet - called
        by every method that references a page it doesn't own the full
        `upsert_page` contract for (links, edges, components, text
        content), same role `duckdb_graph_store.py::_ensure_page` played.
        Details: docs/dev/database/ladybug/page.md#_ensure_page
        """
        conn.execute("MERGE (p:Page {url: $url}) ON CREATE SET p.status = 'Pending'", {"url": url})

    def upsert_page(
        self,
        url: str,
        status: str = "Pending",
        components: int = 0,
        description: str = "",
        title: str = "",
    ) -> None:
        """Create or update a page node; never clobbers Finished with
        Pending, same contract `GraphStore.upsert_page` documents.
        `context`/`label` are gone - see the storage-migration plan for
        why (both dead: `context` had zero readers anywhere, `label` had
        zero writers including its own dedicated `get_page_label`, which
        also had zero callers).
        Details: docs/dev/database/ladybug/page.md#upsert_page
        """
        params = {
            "url": url, "status": status, "components": components,
            "description": description, "title": title,
            "caption": title or url, "visited_at": now() if status == "Finished" else None,
        }

        def op(conn) -> None:
            conn.execute(
                """
                MERGE (p:Page {url: $url})
                ON CREATE SET p.status = $status, p.component_count = $components,
                              p.description = $description, p.title = $title,
                              p.caption = $caption, p.visited_at = $visited_at
                ON MATCH SET
                    p.status = CASE WHEN $status <> 'Pending' THEN $status ELSE p.status END,
                    p.component_count = CASE WHEN $status <> 'Pending' THEN $components ELSE p.component_count END,
                    p.description = CASE WHEN $description <> '' THEN $description ELSE p.description END,
                    p.title = CASE WHEN $title <> '' THEN $title ELSE p.title END,
                    p.caption = CASE WHEN $title <> '' THEN $title ELSE coalesce(p.caption, $url) END,
                    p.visited_at = CASE WHEN $status = 'Finished' THEN $visited_at ELSE p.visited_at END
                """,
                params,
            )

        self._call(op)

    def record_page_metadata(self, page_url: str, metadata: Dict[str, str]) -> None:
        """Store a page's `<meta>` tags as a single `MAP` property.
        Details: docs/dev/database/ladybug/page.md#record_page_metadata
        """
        keys, values = list(metadata.keys()), list(metadata.values())

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            conn.execute(
                "MATCH (p:Page {url: $url}) SET p.metadata = map($keys, $values)",
                {"url": page_url, "keys": keys, "values": values},
            )

        self._call(op)

    def record_link(self, from_url: str, to_url: str, label: str) -> None:
        """Record a discovered link and its visible text, distinct from a
        taken navigation.
        Details: docs/dev/database/ladybug/page.md#record_link
        """
        self.record_links(from_url, [{"to_url": to_url, "label": label}])

    def record_links(self, from_url: str, links: List[Dict[str, str]]) -> None:
        """Batched `record_link`: each item is `{"to_url", "label"}`. A
        real `UNWIND` batch, not the `GraphStore` ABC's own per-item
        default loop - `record_components`' own batching already sets the
        precedent that a whole discovery pass's links are worth one
        round-trip, not one per link.
        Details: docs/dev/database/ladybug/page.md#record_links
        """
        if not links:
            return
        rows = [{"to_url": link["to_url"], "label": link.get("label", "")} for link in links]

        def op(conn) -> None:
            self._ensure_page(conn, from_url)
            for row in rows:
                self._ensure_page(conn, row["to_url"])
            conn.execute(
                """
                UNWIND $rows AS r
                MATCH (from:Page {url: $from_url}), (to:Page {url: r.to_url})
                MERGE (from)-[link:LINKS_TO]->(to)
                SET link.label = r.label
                """,
                {"rows": rows, "from_url": from_url},
            )

        self._call(op)

    def record_edge(self, from_url: str, to_url: str, component: str, action: str, run_id: str = "") -> None:
        """Record a successful navigation; idempotent per `(from, to,
        component, action)` - a transition observed again bumps
        `observation_count` rather than adding a second edge, same
        contract `GraphStore.record_edge` documents.
        Details: docs/dev/database/ladybug/page.md#record_edge
        """
        now_value = now()

        def op(conn) -> None:
            self._ensure_page(conn, from_url)
            self._ensure_page(conn, to_url)
            conn.execute(
                """
                MATCH (from:Page {url: $from_url}), (to:Page {url: $to_url})
                MERGE (from)-[e:NAVIGATES_TO {component: $component, action: $action}]->(to)
                ON CREATE SET e.observation_count = 1, e.first_seen_run = $run_id,
                              e.last_seen_run = $run_id, e.created_at = $now
                ON MATCH SET e.observation_count = e.observation_count + 1,
                             e.last_seen_run = CASE WHEN $run_id <> '' THEN $run_id ELSE e.last_seen_run END
                """,
                {
                    "from_url": from_url, "to_url": to_url, "component": component,
                    "action": action, "run_id": run_id, "now": now_value,
                },
            )

        self._call(op)

    def is_visited(self, url: str) -> bool:
        """Whether this page has concluded (Finished or Failed) and should
        not be queued or visited again.
        Details: docs/dev/database/ladybug/page.md#is_visited
        """
        def op(conn) -> bool:
            rows = list(conn.execute("MATCH (p:Page {url: $url}) RETURN p.status", {"url": url}))
            return bool(rows) and rows[0][0] in ("Finished", "Failed")

        return self._call(op)
