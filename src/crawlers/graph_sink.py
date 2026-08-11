"""Live `GraphStore` wiring for `MechanicalCrawler` - a tracker and a writer.
Details: docs/dev/crawlers/graph_sink.md#module
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.interfaces import ComponentFacts, GraphStore
from ..generators.component_classifier import (
    classify_component_type,
    group_choice_sets,
    group_option_families,
    group_steppers,
)
from ..utils.urls import clean_url


def _component_facts(comp: Dict[str, Any]) -> ComponentFacts:
    """Map one JS-discovered component dict's attribute/style facts onto `ComponentFacts`.
    `value` is deliberately left out: a fill's actual value is already captured by
    `record_component_interaction` at the moment it's set, which is the reliable source -
    re-reading a live `.value` here would just be a second, possibly-stale copy of the
    same fact (discovery can run before or after a fill).
    Details: docs/dev/crawlers/graph_sink.md#_component_facts
    """
    attributes = comp.get("attributes") or {}
    style = comp.get("style") or {}
    return ComponentFacts(
        css_class=attributes.get("class", ""),
        element_id=attributes.get("id", ""),
        href=attributes.get("href", ""),
        placeholder=comp.get("placeholder", ""),
        label=comp.get("label", ""),
        name=comp.get("name", ""),
        disabled=bool(comp.get("disabled", False)),
        required=bool(comp.get("required", False)),
        form=comp.get("form", ""),
        color=style.get("color", ""),
        background_color=style.get("background_color", ""),
        font_size=style.get("font_size", ""),
        font_weight=style.get("font_weight", ""),
        display=style.get("display", ""),
        position=style.get("position", ""),
    )


class GraphStoreInteractionTracker:
    """`InteractionTracker` backed by `GraphStore` reads, with a per-instance
    local read cache. Details: docs/dev/crawlers/graph_sink.md#graphstoreinteractiontracker
    """

    def __init__(self, graph_store: GraphStore, site: str) -> None:
        self.graph_store = graph_store
        self.site = site
        # page_url -> {path: {..., "interacted": bool}}, populated lazily.
        self._states_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._visited_cache: Dict[str, bool] = {}  # page_url -> bool, same discipline.

    def _states_for(self, page_url: str) -> Dict[str, Dict[str, Any]]:
        if page_url not in self._states_cache:
            self._states_cache[page_url] = self.graph_store.get_component_states(self.site, page_url)
        return self._states_cache[page_url]

    def is_interacted(self, page_url: str, path: str) -> bool:
        return bool(self._states_for(page_url).get(path, {}).get("interacted"))

    def mark_interacted(self, page_url: str, path: str) -> None:
        """Cache-only; `GraphStoreSink.record_interaction` does the real write.
        Details: docs/dev/crawlers/graph_sink.md#mark_interacted
        """
        self._states_cache.setdefault(page_url, {}).setdefault(path, {})["interacted"] = True

    def is_visited(self, page_url: str) -> bool:
        if page_url not in self._visited_cache:
            self._visited_cache[page_url] = self.graph_store.is_visited(self.site, page_url)
        return self._visited_cache[page_url]

    def mark_visited(self, page_url: str) -> None:
        """Cache-only; `GraphStoreSink.record_page_finished` does the real write.
        Details: docs/dev/crawlers/graph_sink.md#mark_visited
        """
        self._visited_cache[page_url] = True


class GraphStoreSink:
    """Writes a `MechanicalCrawler` crawl's facts into `GraphStore` as they happen.
    Details: docs/dev/crawlers/graph_sink.md#graphstoresink
    """

    def __init__(self, graph_store: GraphStore, site: str) -> None:
        self.graph_store = graph_store
        self.site = site
        # page_url -> {member_path: representative_path}, populated by
        # record_inventory. Details: docs/dev/crawlers/graph_sink.md#_resolve_write_path
        self._representative_for: Dict[str, Dict[str, str]] = {}

    async def _write(self, fn: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        """Run one blocking `GraphStore` write off the event loop.
        `GraphStore` backends (e.g. `Neo4jGraphStore`) are synchronous - each
        call is its own network round-trip - so calling `fn` directly here
        would stall every other crawl worker sharing this event loop for the
        duration. Details: docs/dev/crawlers/graph_sink.md#_write
        """
        await asyncio.to_thread(fn, *args, **kwargs)

    async def record_page_arrival(self, page_key: str, description: str = "", title: str = "") -> None:
        """Cheapest "this page exists" signal, called before discovery/interaction.
        Details: docs/dev/crawlers/graph_sink.md#record_page_arrival
        """
        await self._write(
            self.graph_store.upsert_page, self.site, page_key,
            status="Pending", description=description, title=title,
        )

    async def record_text_content(self, page_key: str, text_content: List[Dict[str, Any]]) -> None:
        """Full static-text inventory, called once per page visit (not per reveal).
        Details: docs/dev/crawlers/graph_sink.md#record_text_content
        """
        entries = []
        for entry in text_content:
            path = entry.get("path")
            if not path:
                continue
            rect = entry.get("rect") or {}
            entries.append({
                "path": path,
                "tag": entry.get("tag", ""),
                "text": entry.get("text", ""),
                "visible": bool(entry.get("visible", True)),
                "x": rect.get("x"),
                "y": rect.get("y"),
                "width": rect.get("width"),
                "height": rect.get("height"),
            })
        if entries:
            await self._write(self.graph_store.record_text_contents, self.site, page_key, entries)

    async def record_inventory(
        self, page_key: str, components: List[Dict[str, Any]], links: List[Dict[str, str]]
    ) -> None:
        """Full, unconditional component + link inventory for one discovery pass.
        Details: docs/dev/crawlers/graph_sink.md#record_inventory
        """
        choice_sets = group_choice_sets(components)
        option_families = group_option_families(components)
        grouped_paths = {
            member.get("path")
            for members in (*choice_sets.values(), *option_families.values())
            for member in members
        }

        component_batch: List[Dict[str, Any]] = []
        for comp in components:
            if comp.get("path") in grouped_paths:
                continue
            args = self._component_args(comp)
            if args is not None:
                component_batch.append(args)

        for stepper in group_steppers(components):
            increment_path = stepper.get("increment_path")
            if increment_path:
                await self._write(
                    self.graph_store.record_component_options,
                    self.site, page_key, increment_path, json.dumps(stepper),
                )

        for name, members in choice_sets.items():
            args = await self._record_choice_group(page_key, name, members)
            if args is not None:
                component_batch.append(args)
        for parent_path, members in option_families.items():
            args = await self._record_choice_group(page_key, parent_path, members)
            if args is not None:
                component_batch.append(args)

        if component_batch:
            await self._write(self.graph_store.record_components, self.site, page_key, component_batch)

        link_batch = []
        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - see mechanical_loop's own identical filter
            if not href:
                continue
            link_batch.append({"to_url": clean_url(href), "label": link.get("text", "")})
        if link_batch:
            await self._write(self.graph_store.record_links, self.site, page_key, link_batch)

    def _component_args(self, comp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """One component's descriptive fields as `record_component(s)` kwargs,
        or `None` if it has no path (nothing to write). Shared by the main
        inventory batch and `_record_choice_group`'s representative entry, so
        a group's node gets exactly the same real tag/text/role/rect/
        component_type an ungrouped component would - no separate "blank
        ghost node" code path for the representative.
        Details: docs/dev/crawlers/graph_sink.md#_component_args
        """
        path = comp.get("path")
        if not path:
            return None
        rect = comp.get("rect") or {}
        return {
            "path": path,
            "tag": comp.get("tag", ""),
            "text": comp.get("text", ""),
            "role": comp.get("role", ""),
            "input_type": comp.get("input_type", ""),
            "visible": bool(comp.get("visible", True)),
            "layer": comp.get("discovery_layer", "semantic"),
            "x": rect.get("x"),
            "y": rect.get("y"),
            "width": rect.get("width"),
            "height": rect.get("height"),
            "component_type": classify_component_type(comp),
            "facts": _component_facts(comp),
        }

    async def _record_choice_group(
        self, page_key: str, group_name: str, members: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Persist one member-list (radio/checkbox set, or a dropdown/menu's
        options) as a single Component node - `members[0]` is the
        representative every member's own path redirects to from now on
        (see `_resolve_write_path`), instead of each member getting its own
        near-identical node differing only by which choice it is. Returns
        the representative's own `record_component(s)` args rather than
        writing them here, so the caller can batch it into the same call as
        every ungrouped component from this discovery pass.
        Details: docs/dev/crawlers/graph_sink.md#_record_choice_group
        """
        representative = members[0]
        representative_path = representative.get("path")
        if not representative_path:
            return None
        args = self._component_args(representative)
        option_summary = json.dumps(
            {
                "group": group_name,
                "options": [
                    {"path": m.get("path"), "text": m.get("text"), "selected": bool(m.get("selected"))}
                    for m in members
                ],
            }
        )
        await self._write(
            self.graph_store.record_component_options, self.site, page_key, representative_path, option_summary
        )
        page_map = self._representative_for.setdefault(page_key, {})
        for member in members:
            member_path = member.get("path")
            if member_path:
                page_map[member_path] = representative_path
        return args

    def _resolve_write_path(self, page_key: str, path: str) -> Tuple[str, str]:
        """Where a path's write actually lands, and which exact member caused
        it. A consolidated dropdown/choice-group member redirects to its
        group's representative node instead of creating its own - the
        original `path` is returned as `source_path` so which specific
        option acted is relocated, not lost.
        Details: docs/dev/crawlers/graph_sink.md#_resolve_write_path
        """
        representative = self._representative_for.get(page_key, {}).get(path)
        if representative and representative != path:
            return representative, path
        return path, ""

    async def record_interaction(self, page_key: str, path: str, action: str, value: str, resulting_url: str) -> None:
        """One call per *attempted* interaction, success or failure.
        Details: docs/dev/crawlers/graph_sink.md#record_interaction
        """
        write_path, source_path = self._resolve_write_path(page_key, path)
        await self._write(
            self.graph_store.record_component_interaction, self.site, page_key, write_path,
            action=action, value=value, resulting_url=resulting_url, source_path=source_path,
        )

    async def record_component_network(self, page_key: str, path: str, requests: List[Dict[str, Any]]) -> None:
        """One call per interaction that triggered >=1 meaningful (xhr/fetch) request.
        Details: docs/dev/crawlers/graph_sink.md#record_component_network
        """
        write_path, source_path = self._resolve_write_path(page_key, path)
        payload = [{**r, "source_path": source_path} for r in requests] if source_path else requests
        await self._write(
            self.graph_store.record_component_network, self.site, page_key, write_path, json.dumps(payload)
        )

    async def record_revealed_options(self, page_key: str, trigger_path: str, revealed: List[Dict[str, Any]]) -> None:
        """Attach a before/after-diff-detected set of revealed options to the trigger.
        Details: docs/dev/crawlers/graph_sink.md#record_revealed_options
        """
        payload = json.dumps({"trigger": trigger_path, "revealed_options": revealed})
        await self._write(self.graph_store.record_component_options, self.site, page_key, trigger_path, payload)

    async def record_navigation_edge(self, from_key: str, to_key: str, path: str, action: str) -> None:
        """Only called when an interaction's resulting URL differs from the page it ran on."""
        await self._write(self.graph_store.record_edge, self.site, from_key, to_key, component=path, action=action)

    async def record_page_finished(self, page_key: str, component_count: int) -> None:
        """Called once a page's pass completes without being cut short by navigation.
        Details: docs/dev/crawlers/graph_sink.md#record_page_finished
        """
        await self._write(
            self.graph_store.upsert_page, self.site, page_key, status="Finished", components=component_count
        )
