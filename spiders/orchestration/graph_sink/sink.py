"""Writes a MechanicalCrawler crawl's facts into GraphStore as they happen.
Details: docs/dev/spiders/orchestration/graph_sink/sink.md#module
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.interfaces import VisitStep
from generators.component_classifier import (
    classify_component_type,
    group_choice_sets,
    group_option_families,
    group_steppers,
)
from utils.urls import is_in_scope, route_shape
from .component_facts import component_facts, option_labels_for

# Status for a link target the frontier will never visit because it points off
# the crawled domain. Without it those pages sit in `Pending` forever - the
# frontier refuses them on scope grounds while this sink records them anyway,
# so `get_pending` returns work that can never be done and `count_visited`
# can never reach 100% on a site that links outward.
# Details: docs/dev/spiders/orchestration/graph_sink/sink.md#external_page_status
EXTERNAL_PAGE_STATUS = "External"

# Status for a page whose interrupted pass exhausted UrlFrontier's
# max_requeue_attempts (a reliably anti-bot-blocked page, or a redirect
# destination too many independent passes kept landing on and requeuing).
# Distinct from "Pending" (get_pending() excludes it, so a resumed run
# doesn't retry it forever) and from "Finished" (coverage/measurement
# passes correctly treat it as never actually analyzed).
# Details: docs/dev/spiders/orchestration/graph_sink/sink.md#failed_page_status
FAILED_PAGE_STATUS = "Failed"

# Status for a page whose scout()-only pass (phase 1 of a two_phase_crawl
# run) has finished discovery + sink bookkeeping but not yet interaction.
# Distinct from "Pending" (still owed a first pass of any kind) and
# "Finished" (interact()'s own trailing record_page_finished call
# overwrites this once phase 2 actually runs the page's interaction
# frontier). is_visited() deliberately does not treat this as concluded.
# Details: docs/dev/spiders/orchestration/graph_sink/sink.md#scouted_page_status
SCOUTED_PAGE_STATUS = "Scouted"


class GraphStoreSink:
    """Writes a `MechanicalCrawler` crawl's facts into `GraphStore` as they happen.
    Details: docs/dev/spiders/orchestration/graph_sink/sink.md#graphstoresink
    """

    def __init__(
        self,
        graph_store: Any,
        base_url: Optional[str] = None,
        allow_subdomains: bool = False,
        run_id: str = "",
    ) -> None:
        self.graph_store = graph_store
        # The same two values `UrlFrontier` gates on, so a link is judged
        # in-scope identically whether it is being queued or recorded.
        # `None` disables the check, preserving the pre-scope behavior for
        # callers that never pass it (tests, mostly).
        # Details: docs/dev/spiders/orchestration/graph_sink/sink.md#base_url
        self.base_url = base_url
        self.allow_subdomains = allow_subdomains
        # Identifies this crawl to record_navigation_edge's run_id - "" for
        # any caller that doesn't track one (tests, mostly), which every
        # GraphStore backend accepts as "no provenance recorded".
        self.run_id = run_id
        # page_url -> {member_path: representative_path}, populated by
        # record_inventory. Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_resolve_write_path
        self._representative_for: Dict[str, Dict[str, str]] = {}

    async def _write(self, fn: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        """Run one blocking `GraphStore` write off the event loop.
        `LadybugGraphStore` is synchronous - it blocks on its own single
        writer thread (see `database/ladybug/writer.py`) - so calling
        `fn` directly here would stall every other crawl worker sharing
        this event loop for the duration.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_write
        """
        await asyncio.to_thread(fn, *args, **kwargs)

    async def record_page_arrival(self, page_key: str, description: str = "", title: str = "") -> None:
        """Cheapest "this page exists" signal, called before discovery/interaction.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_arrival
        """
        await self._write(
            self.graph_store.upsert_page, page_key,
            status="Pending", description=description, title=title,
        )

    async def record_page_metadata(self, page_key: str, metadata: Dict[str, str]) -> None:
        """The page's own `<meta>` tags - extracted on every navigation
        since long before anything stored them.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_metadata
        """
        if not metadata:
            return
        await self._write(self.graph_store.record_page_metadata, page_key, metadata)

    def _mark_party(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stamp `is_first_party` onto each already-filtered request dict,
        by the same `base_url`/`allow_subdomains` host check `record_inventory`
        already applies to link targets - reused rather than introducing a
        second notion of "this site". `GraphStore` reads the stamp to decide
        whether a request earns its own `Request` node or only bumps its
        `Endpoint`'s `call_count` - see `database/ladybug/network.py`.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_mark_party
        """
        return [{**r, "is_first_party": self._is_first_party_host(r.get("host", ""))} for r in requests]

    def _is_first_party_host(self, host: str) -> bool:
        """No `base_url` configured means no scope was ever declared -
        treated as first-party, the same permissive default `record_inventory`'s
        own off-site check already applies when `self.base_url` is falsy."""
        return not self.base_url or is_in_scope(host, self.base_url, self.allow_subdomains)

    async def record_page_network(self, page_key: str, requests: List[Dict[str, Any]]) -> None:
        """Requests the page's own load fired, with no component to blame.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_network
        """
        if not requests:
            return
        await self._write(self.graph_store.record_page_network, page_key, self._mark_party(requests))

    async def record_text_content(self, page_key: str, text_content: List[Dict[str, Any]]) -> None:
        """Full static-text inventory, called once per page visit (not per reveal).
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_text_content
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
            await self._write(self.graph_store.record_text_contents, page_key, entries)

    async def record_state_styles(self, page_key: str, pseudo_styles: List[Dict[str, Any]]) -> None:
        """Declared `:hover`/`:focus` values, called once per page visit.

        Same cadence as `record_text_content` and for the same reason: these
        come from the page's stylesheets, which a click cannot change, so
        re-recording them per reveal would write identical rows repeatedly.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_state_styles
        """
        if pseudo_styles:
            await self._write(self.graph_store.record_state_styles, page_key, pseudo_styles)

    async def record_inventory(
        self, page_key: str, components: List[Dict[str, Any]], links: List[Dict[str, str]]
    ) -> None:
        """Full, unconditional component + link inventory for one discovery pass.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_inventory
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
                    page_key, increment_path, stepper,
                    option_labels=option_labels_for(json.dumps(stepper)),
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
            await self._write(self.graph_store.record_components, page_key, component_batch)

        # Structural containment, keyed to exactly the paths that got a
        # Component row above: every ungrouped component's own ancestors,
        # plus each choice-group/stepper-family's representative (the only
        # member of the group with a row of its own - see _record_choice_group).
        # A member consolidated into a group never gets its own row, so its
        # ancestors would be orphaned data with nothing to join against.
        ancestor_entries = [
            {"path": comp["path"], "ancestors": comp["ancestors"]}
            for comp in components
            if comp.get("path") and comp.get("ancestors") and comp["path"] not in grouped_paths
        ]
        for members in (*choice_sets.values(), *option_families.values()):
            representative = members[0]
            if representative.get("path") and representative.get("ancestors"):
                ancestor_entries.append(
                    {"path": representative["path"], "ancestors": representative["ancestors"]}
                )
        if ancestor_entries:
            await self._write(self.graph_store.record_component_ancestors, page_key, ancestor_entries)

        link_batch = []
        off_site: List[str] = []
        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - see mechanical_loop's own identical filter
            if not href:
                continue
            # route_shape, not clean_url: every other page key in the graph
            # is shaped (visit() derives page_key that way), so recording a
            # link target unshaped would mint a second node for a screen that
            # already has a canonical one - exactly what route_shape exists to
            # prevent. Details: docs/dev/spiders/orchestration/graph_sink/sink.md#link-target-key
            target = route_shape(href)
            link_batch.append({"to_url": target, "label": link.get("text", "")})
            if self.base_url and not is_in_scope(href, self.base_url, self.allow_subdomains):
                off_site.append(target)
        if link_batch:
            await self._write(self.graph_store.record_links, page_key, link_batch)
        # After record_links, never instead of it: the edge to an off-site
        # page is real data (where this site sends you) and stays recorded.
        # Only the target's status changes, so it stops posing as work.
        # Details: docs/dev/spiders/orchestration/graph_sink/sink.md#off-site-targets
        for url in dict.fromkeys(off_site):
            await self._write(self.graph_store.upsert_page, url, status=EXTERNAL_PAGE_STATUS)

    def _component_args(self, comp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """One component's descriptive fields as `record_component(s)` kwargs,
        or `None` if it has no path (nothing to write). Shared by the main
        inventory batch and `_record_choice_group`'s representative entry, so
        a group's node gets exactly the same real tag/text/role/rect/
        component_type an ungrouped component would - no separate "blank
        ghost node" code path for the representative.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_component_args
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
            "facts": component_facts(comp),
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
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_record_choice_group
        """
        representative = members[0]
        representative_path = representative.get("path")
        if not representative_path:
            return None
        args = self._component_args(representative)
        option_summary = {
            "group": group_name,
            "options": [
                {"path": m.get("path"), "text": m.get("text"), "selected": bool(m.get("selected"))}
                for m in members
            ],
        }
        await self._write(
            self.graph_store.record_component_options, page_key, representative_path, option_summary,
            option_labels=option_labels_for(json.dumps(option_summary)),
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
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#_resolve_write_path
        """
        representative = self._representative_for.get(page_key, {}).get(path)
        if representative and representative != path:
            return representative, path
        return path, ""

    async def record_interaction(
        self, page_key: str, path: str, action: str, value: str, resulting_url: str,
        step: Optional[VisitStep] = None,
    ) -> None:
        """One call per *attempted* interaction, success or failure.
        `step` places it in its visit's sequence - see `VisitStep`.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_interaction
        """
        write_path, source_path = self._resolve_write_path(page_key, path)
        await self._write(
            self.graph_store.record_component_interaction, page_key, write_path,
            action=action, value=value, resulting_url=resulting_url, source_path=source_path,
            step=step,
        )

    async def record_component_network(
        self, page_key: str, path: str, requests: List[Dict[str, Any]],
        step: Optional[VisitStep] = None,
    ) -> None:
        """One call per interaction that triggered >=1 meaningful (xhr/fetch) request.

        Each request is stamped with the interaction's own `step` before
        being written. That stamp is what lets a reader tell which request
        belongs to which interaction after the store flattens every batch
        into one list - without it, a control clicked twice pools its
        responses and neither can be attributed.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_component_network
        """
        if step is not None:
            requests = [
                {**request, "visit_id": step.visit_id, "step_seq": step.seq} for request in requests
            ]
        write_path, source_path = self._resolve_write_path(page_key, path)
        payload = [{**r, "source_path": source_path} for r in requests] if source_path else requests
        await self._write(
            self.graph_store.record_component_network, page_key, write_path, self._mark_party(payload)
        )

    async def record_revealed_options(self, page_key: str, trigger_path: str, revealed: List[Dict[str, Any]]) -> None:
        """Attach a before/after-diff-detected set of revealed options to the trigger.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_revealed_options
        """
        payload = {"trigger": trigger_path, "revealed_options": revealed}
        await self._write(
            self.graph_store.record_component_options, page_key, trigger_path, payload,
            option_labels=option_labels_for(json.dumps(payload)),
        )

    async def record_navigation_edge(self, from_key: str, to_key: str, path: str, action: str) -> None:
        """Only called when an interaction's resulting URL differs from the page it ran on."""
        await self._write(
            self.graph_store.record_edge, from_key, to_key,
            component=path, action=action, run_id=self.run_id,
        )

    async def record_page_finished(self, page_key: str, component_count: int) -> None:
        """Called once a page's pass completes without being cut short by navigation.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_finished
        """
        await self._write(self.graph_store.upsert_page, page_key, status="Finished", components=component_count)

    async def record_page_failed(self, page_key: str) -> None:
        """Called once `UrlFrontier.requeue` gives up on a page for good -
        see `FAILED_PAGE_STATUS`. Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_failed
        """
        await self._write(self.graph_store.upsert_page, page_key, status=FAILED_PAGE_STATUS)

    async def record_page_scouted(self, page_key: str, component_count: int) -> None:
        """Called once `scout()`'s discovery + bookkeeping pass completes for
        a page - never interrupted the way `interact()` can be, so this is
        unconditional. Mirrors `record_page_finished`'s own shape/params.
        Details: docs/dev/spiders/orchestration/graph_sink/sink.md#record_page_scouted
        """
        await self._write(
            self.graph_store.upsert_page, page_key, status=SCOUTED_PAGE_STATUS, components=component_count
        )
