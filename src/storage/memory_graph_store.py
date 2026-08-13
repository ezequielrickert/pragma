"""In-memory GraphStore: the default backend, and the reference for the Neo4j one.
Details: docs/dev/storage/memory_graph_store.md#module
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..core.interfaces import ComponentFacts, ComponentFamily, GraphStore, InferredRequest
from ..core.registry import GRAPH_STORE_REGISTRY

# ComponentFacts field names, in the fixed order every component record
# stores/returns them - the single place both `_new_component_record` and
# `record_component` derive their facts dict from, so the two can't drift.
_FACTS_FIELDS: Tuple[str, ...] = tuple(ComponentFacts.__dataclass_fields__.keys())


@dataclass
class _SiteData:
    routes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    links: Dict[Tuple[str, str], str] = field(default_factory=dict)
    # {page_url: {path: {tag, text, role, input_type, visible, layer, x, y, width,
    # height, component_type, options, interacted, interactions, network_requests}}}
    components: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    # {page_url: [{path, tag, text, visible, x, y, width, height}]}
    text_content: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    # {page_url: [request, ...]} for requests the page's own load fired.
    page_network: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    # {page_url: [violation, ...]} from the measurement pass's axe run.
    accessibility: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    component_families: List[ComponentFamily] = field(default_factory=list)
    inferred_requests: List[InferredRequest] = field(default_factory=list)


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
        description: str = "",
        title: str = "",
    ) -> None:
        routes = self._site(site).routes
        if url not in routes or status != "Pending":
            routes[url] = {
                "status": status,
                "components": components,
                "visited": "2026-05-17" if status == "Finished" else "-",
                "context": context or routes.get(url, {}).get("context", "-"),
                "label": label or routes.get(url, {}).get("label", "-"),
                "description": description or routes.get(url, {}).get("description", ""),
                "title": title or routes.get(url, {}).get("title", ""),
            }

    def get_page_descriptions(self, site: str) -> Dict[str, str]:
        return {
            url: data["description"]
            for url, data in self._site(site).routes.items()
            if data.get("description")
        }

    def get_page_titles(self, site: str) -> Dict[str, str]:
        return {
            url: data["title"]
            for url, data in self._site(site).routes.items()
            if data.get("title")
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
        """Fresh default record for a path first touched via an auto-create path.
        Details: docs/dev/storage/memory_graph_store.md#_new_component_record
        """
        return {
            "tag": "", "text": "", "role": "", "input_type": "",
            "visible": True, "layer": "semantic",
            "x": None, "y": None, "width": None, "height": None,
            "component_type": "", "options": "", "option_labels": [],
            "interacted": False, "interactions": [], "network_requests": [],
            **asdict(ComponentFacts()),
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
        facts: Optional[ComponentFacts] = None,
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
            "option_labels": existing["option_labels"] if existing else [],
            "interacted": existing["interacted"] if existing else False,
            "interactions": existing["interactions"] if existing else [],
            "network_requests": existing["network_requests"] if existing else [],
            **asdict(facts or ComponentFacts()),
        }

    def record_component_interaction(
        self,
        site: str,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
        source_path: str = "",
    ) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        record = page_components.setdefault(path, self._new_component_record())
        record["interacted"] = True
        # `source_path` is always present, even blank - the Neo4j backend now
        # reads interactions off :INTERACTED relationships, where every
        # property exists on every edge, and the two backends must hand back
        # the same shape. Every reader already treats "" as absent.
        # Details: docs/dev/storage/memory_graph_store.md#record_component_interaction
        record["interactions"].append(
            {"action": action, "value": value, "resulting_url": resulting_url, "source_path": source_path}
        )

    def record_accessibility_violations(self, site: str, page_url: str, violations_json: str) -> None:
        self._site(site).accessibility[page_url] = json.loads(violations_json)

    def get_accessibility_violations(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        return {url: list(v) for url, v in self._site(site).accessibility.items() if v}

    def record_page_network(self, site: str, page_url: str, requests_json: str) -> None:
        self._site(site).page_network.setdefault(page_url, []).extend(json.loads(requests_json))

    def get_page_network_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        return {url: list(requests) for url, requests in self._site(site).page_network.items() if requests}

    def record_component_options(
        self, site: str, page_url: str, path: str, options: str, option_labels: Optional[List[str]] = None
    ) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        record = page_components.setdefault(path, self._new_component_record())
        record["options"] = options
        record["option_labels"] = list(option_labels or [])

    def record_component_network(self, site: str, page_url: str, path: str, requests_json: str) -> None:
        page_components = self._site(site).components.setdefault(page_url, {})
        record = page_components.setdefault(path, self._new_component_record())
        record.setdefault("network_requests", []).extend(json.loads(requests_json))

    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        return {
            path: {
                "tag": r["tag"], "text": r["text"], "interacted": r["interacted"], "visible": r["visible"],
                "x": r.get("x"), "y": r.get("y"), "width": r.get("width"), "height": r.get("height"),
                "component_type": r.get("component_type", ""), "options": r.get("options", ""),
                "option_labels": list(r.get("option_labels", [])),
                "network_requests": list(r.get("network_requests", [])),
                **{name: r.get(name) for name in _FACTS_FIELDS},
            }
            for path, r in self._site(site).components.get(page_url, {}).items()
        }

    def _iter_components(self, site: str, semantic_only: bool):
        for page_components in self._site(site).components.values():
            for record in page_components.values():
                if semantic_only and record.get("layer") == "pointer":
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
                if not record["interacted"] and not (semantic_only and record.get("layer") == "pointer")
            )
            if count:
                counts.append({"url": page_url, "unexplored_count": count})
        counts.sort(key=lambda row: row["unexplored_count"], reverse=True)
        return counts if limit is None else counts[:limit]

    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        for record in self._site(site).components.get(url, {}).values():
            if semantic_only and record.get("layer") == "pointer":
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
                    "option_labels": list(r.get("option_labels", [])),
                    "network_requests": list(r.get("network_requests", [])),
                    **{name: r.get(name) for name in _FACTS_FIELDS},
                }
                for path, r in page_components.items()
            }
            for page_url, page_components in self._site(site).components.items()
        }

    def record_component_families(self, site: str, families: List[ComponentFamily]) -> None:
        """Overwrite `site`'s whole family list with `families` - a plain
        assignment, since there's no incident-relationship bookkeeping to
        clean up the way `Neo4jGraphStore`'s DETACH DELETE-then-recreate
        needs. `families=[]` clears everything for `site`, same full-
        rebuild contract as the Neo4j backend
        (docs/dev/core/interfaces.md#record_component_families).
        """
        self._site(site).component_families = list(families)

    def get_component_families(self, site: str) -> List[ComponentFamily]:
        """Every `ComponentFamily` last written for `site` via
        `record_component_families`, in that same call's order (this
        backend never reorders them - unlike `Neo4jGraphStore.
        get_component_families`, whose `member_paths` are re-sorted on
        every read; here they're already sorted, since
        `component_family.build_component_families` sorts before
        returning). `[]` if `record_component_families` was never called,
        or was last called with an empty list.
        """
        return list(self._site(site).component_families)

    def record_inferred_requests(self, site: str, requests: List[InferredRequest]) -> None:
        """Overwrite `site`'s whole inferred-request list - same plain-
        assignment, full-replace discipline as `record_component_families`.
        """
        self._site(site).inferred_requests = list(requests)

    def get_inferred_requests(self, site: str) -> List[InferredRequest]:
        """Every `InferredRequest` last written for `site`. `[]` if
        `record_inferred_requests` was never called."""
        return list(self._site(site).inferred_requests)

    def record_text_content(
        self,
        site: str,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        visible: bool = True,
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> None:
        entries = self._site(site).text_content.setdefault(page_url, [])
        record = {
            "path": path, "tag": tag, "text": text, "visible": visible,
            "x": x, "y": y, "width": width, "height": height,
        }
        for i, existing in enumerate(entries):
            if existing["path"] == path:
                entries[i] = record
                return
        entries.append(record)

    def get_text_content_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        return {
            page_url: [dict(entry) for entry in entries]
            for page_url, entries in self._site(site).text_content.items()
        }
