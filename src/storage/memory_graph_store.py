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
    # {page_url: {path: {tag, text, role, input_type, visible, layer, x, y, width,
    # height, component_type, options, interacted, interactions}}}
    components: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)


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

    def clear_site(self, site: str) -> None:
        self._sites.pop(site, None)

    @staticmethod
    def _new_component_record() -> Dict[str, Any]:
        """A fresh default record for a path first touched via
        `record_component_interaction`/`record_component_options` rather than
        `record_component` - a plain dict literal, not a shared class-level
        default, since `interactions` is a mutable list every record needs
        its own instance of, not one aliased across every auto-created path."""
        return {
            "tag": "", "text": "", "role": "", "input_type": "",
            "visible": True, "layer": "semantic",
            "x": None, "y": None, "width": None, "height": None,
            "component_type": "", "options": "",
            "interacted": False, "interactions": [],
            "excluded_from_debt": False,
        }

    def record_component(
        self,
        site: str,
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
    ) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        existing = page_components.get(path)
        page_components[path] = {
            "tag": tag,
            "text": text,
            "role": role,
            "input_type": input_type,
            "visible": visible,
            "layer": layer,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "component_type": component_type,
            "options": existing["options"] if existing else "",
            "interacted": existing["interacted"] if existing else False,
            "interactions": existing["interactions"] if existing else [],
            "excluded_from_debt": existing["excluded_from_debt"] if existing else False,
        }

    def record_component_interaction(
        self,
        site: str,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
    ) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        record = page_components.setdefault(path, self._new_component_record())
        record["interacted"] = True
        record["interactions"].append(
            {"action": action, "value": value, "resulting_url": resulting_url}
        )

    def record_component_options(
        self, site: str, page_url: str, path: str, options: str, excluded_from_debt: bool = False
    ) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        record = page_components.setdefault(path, self._new_component_record())
        record["options"] = options
        record["excluded_from_debt"] = excluded_from_debt

    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        return {
            path: {
                "tag": r["tag"], "text": r["text"], "interacted": r["interacted"], "visible": r["visible"],
                "x": r.get("x"), "y": r.get("y"), "width": r.get("width"), "height": r.get("height"),
                "component_type": r.get("component_type", ""), "options": r.get("options", ""),
                "excluded_from_debt": r.get("excluded_from_debt", False),
            }
            for path, r in self._site(site).components.get(page_url, {}).items()
        }

    def _iter_components(self, site: str, semantic_only: bool):
        for page_components in self._site(site).components.values():
            for record in page_components.values():
                if semantic_only and record.get("layer") == "pointer":
                    continue
                # A grouped member (e.g. one of a revealed dropdown's options - see
                # record_component_options' `excluded_from_debt` docstring) is still a
                # real, listed Component - it just never counts as its own unit of
                # "unexplored work," since interacting with the group's trigger already
                # covers it.
                if record.get("excluded_from_debt"):
                    continue
                yield record

    def count_unexplored_components(self, site: str, semantic_only: bool = True) -> Tuple[int, int]:
        total = 0
        unexplored = 0
        for record in self._iter_components(site, semantic_only):
            total += 1
            if not record["interacted"]:
                unexplored += 1
        return unexplored, total

    def get_pages_with_unexplored_components(
        self, site: str, limit: Optional[int] = None, semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        counts: List[Dict[str, Any]] = []
        for page_url, page_components in self._site(site).components.items():
            count = sum(
                1
                for record in page_components.values()
                if not record["interacted"]
                and not (semantic_only and record.get("layer") == "pointer")
                and not record.get("excluded_from_debt")
            )
            if count:
                counts.append({"url": page_url, "unexplored_count": count})
        counts.sort(key=lambda row: row["unexplored_count"], reverse=True)
        return counts if limit is None else counts[:limit]

    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        for record in self._site(site).components.get(url, {}).values():
            if semantic_only and record.get("layer") == "pointer":
                continue
            if record.get("excluded_from_debt"):
                continue
            if not record["interacted"]:
                return True
        return False

    def get_component_ledger(self, site: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return {
            page_url: {
                path: {
                    "tag": r["tag"], "text": r["text"],
                    "interacted": r["interacted"], "interactions": list(r["interactions"]),
                    "x": r.get("x"), "y": r.get("y"), "width": r.get("width"), "height": r.get("height"),
                    "component_type": r.get("component_type", ""), "options": r.get("options", ""),
                    "excluded_from_debt": r.get("excluded_from_debt", False),
                }
                for path, r in page_components.items()
            }
            for page_url, page_components in self._site(site).components.items()
        }
