"""In-memory GraphStore: the default backend, and the reference for the Neo4j one.

Reproduces the exact dict-based tracking Pragma used before Neo4j support was
added (one flat routes/edges pair per site instead of one shared pair), so
runs and tests without a live Neo4j instance behave identically to before.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..core.interfaces import GraphStore
from ..core.registry import GRAPH_STORE_REGISTRY


@dataclass
class _SiteData:
    routes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    links: Dict[Tuple[str, str], str] = field(default_factory=dict)


@GRAPH_STORE_REGISTRY.register("memory")
class InMemoryGraphStore(GraphStore):
    """Process-local GraphStore, scoped per site. No persistence across runs."""

    def __init__(self) -> None:
        self._sites: Dict[str, _SiteData] = {}

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def _site(self, site: str) -> _SiteData:
        return self._sites.setdefault(site, _SiteData())

    def upsert_page(
        self,
        site: str,
        url: str,
        status: str = "Pending",
        components: int = 0,
        context: str = "",
        label: str = "",
    ) -> None:
        routes = self._site(site).routes
        if url not in routes or status != "Pending":
            routes[url] = {
                "status": status,
                "components": components,
                "visited": "2026-05-17" if status == "Finished" else "-",
                "context": context or routes.get(url, {}).get("context", "-"),
                "label": label or routes.get(url, {}).get("label", "-"),
            }

    def is_visited(self, site: str, url: str) -> bool:
        return self._site(site).routes.get(url, {}).get("status") == "Finished"

    def get_pending(self, site: str, limit: Optional[int] = None) -> List[str]:
        pending = sorted(u for u, d in self._site(site).routes.items() if d["status"] == "Pending")
        return pending if limit is None else pending[:limit]

    def get_page_label(self, site: str, url: str) -> Optional[str]:
        page = self._site(site).routes.get(url)
        return page["label"] if page else None

    def record_link(self, site: str, from_url: str, to_url: str, label: str) -> None:
        self._site(site).links[(from_url, to_url)] = label

    def get_link_label(self, site: str, from_url: str, to_url: str) -> Optional[str]:
        return self._site(site).links.get((from_url, to_url))

    def record_edge(self, site: str, from_url: str, to_url: str, component: str, action: str) -> None:
        for endpoint in (from_url, to_url):
            self.upsert_page(site, endpoint)
        self._site(site).edges.append(
            {"from": from_url, "component": component, "action": action, "to": to_url}
        )

    def get_edges(self, site: str) -> List[Dict[str, str]]:
        return list(self._site(site).edges)

    def get_progress_table_rows(self, site: str) -> List[Dict[str, Any]]:
        rows = sorted(self._site(site).routes.items(), key=lambda x: (x[1]["status"] != "Finished", x[0]))
        return [{"url": url, **data} for url, data in rows]

    def count_visited(self, site: str) -> Tuple[int, int]:
        routes = self._site(site).routes
        finished = sum(1 for d in routes.values() if d["status"] == "Finished")
        return finished, len(routes)

    def get_loop_signals(self, site: str, url: str) -> List[Dict[str, str]]:
        seen: List[Dict[str, str]] = []
        seen_pairs = set()
        for edge in self._site(site).edges:
            if edge["to"] != url:
                continue
            pair = (edge["component"], edge["from"])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                seen.append({"component": edge["component"], "from": edge["from"]})
        return seen
