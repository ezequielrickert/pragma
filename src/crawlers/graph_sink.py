"""Phase 3 of the crawl4ai migration: live `GraphStore` wiring for
`MechanicalCrawler` - Neo4j (or `InMemoryGraphStore`) becomes the crawl's
source of truth, written to as the crawl happens rather than batched by an
in-process orchestrator afterward.

Two small, separately-testable pieces:
- `GraphStoreInteractionTracker` - the `InteractionTracker` seam
  `mechanical_loop.py` already defines, backed by `GraphStore` reads instead
  of an in-memory dict, so "have I already interacted with this" survives
  across a persisted multi-run crawl, not just within one process (see
  wiki/graph-based-crawl-tracking.md's "the ledger must be consulted, not
  write-only"). Its `mark_interacted`/`mark_visited` are deliberate no-ops -
  see their docstrings - because `GraphStoreSink` below is what actually
  performs the detail-rich write in each case (with `action`/`value`/
  `resulting_url` the plain `InteractionTracker` protocol has no room for);
  routing "mark" through here too would mean recording every interaction
  twice, once thin and once rich.
- `GraphStoreSink` - the detail-rich writer `MechanicalCrawler` calls
  directly at each point in the plan's hook-mapping table (page arrival,
  full component/link inventory, each interaction, navigation edges, page
  completion).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.interfaces import GraphStore
from ..generators.component_classifier import (
    classify_component_type,
    group_choice_sets,
    group_steppers,
)
from ..utils.urls import clean_url


class GraphStoreInteractionTracker:
    """`InteractionTracker` backed by `GraphStore` reads - see module
    docstring for why its write methods are no-ops."""

    def __init__(self, graph_store: GraphStore, site: str) -> None:
        self.graph_store = graph_store
        self.site = site

    def is_interacted(self, page_url: str, path: str) -> bool:
        states = self.graph_store.get_component_states(self.site, page_url)
        return bool(states.get(path, {}).get("interacted"))

    def mark_interacted(self, page_url: str, path: str) -> None:
        """No-op: `GraphStoreSink.record_interaction` is what actually calls
        `GraphStore.record_component_interaction` for every attempted
        interaction (success or failure), with the full `action`/`value`/
        `resulting_url` detail this protocol method doesn't carry. Marking
        here too would be a second, thinner write for the same fact.
        """

    def is_visited(self, page_url: str) -> bool:
        return self.graph_store.is_visited(self.site, page_url)

    def mark_visited(self, page_url: str) -> None:
        """No-op: `GraphStoreSink.record_page_finished` is what actually
        calls `GraphStore.upsert_page(..., status="Finished", ...)` - see
        that method's docstring for why it needs the final component count,
        which this protocol method doesn't carry.
        """


class GraphStoreSink:
    """Writes a `MechanicalCrawler` crawl's facts into `GraphStore` as they
    happen. Every method maps directly to one row of the plan's "which
    crawl4ai hook maps to which GraphStore call" table, just invoked from
    `MechanicalCrawler`'s own Python-side orchestration (not a crawl4ai hook
    itself) since it needs the actual interaction *result* (did the URL
    change), which only exists once `crawler.click()`/`fill()` returns.
    """

    def __init__(self, graph_store: GraphStore, site: str) -> None:
        self.graph_store = graph_store
        self.site = site

    def record_page_arrival(self, page_key: str, description: str = "", title: str = "") -> None:
        """Cheapest possible "this page exists" signal - called the moment a
        page is reached, before discovery/interaction. A bare rediscovery
        (status="Pending") never clobbers an already-Finished page, per
        `GraphStore.upsert_page`'s own contract - same discipline now applies
        to `description` (added for the PRD synthesizer, which reads it back
        via `get_page_descriptions` instead of an in-process attribute that
        would die with the crawling process) and to `title` (the page's own
        `<title>`, read back via `get_page_titles` - the document renderer's
        "name of this page," distinct from `label`'s per-incoming-link anchor
        text).
        """
        self.graph_store.upsert_page(self.site, page_key, status="Pending", description=description, title=title)

    def record_text_content(self, page_key: str, text_content: List[Dict[str, Any]]) -> None:
        """Full, unconditional static-text inventory - called once per page
        visit (see `MechanicalCrawler._visit_page`), not re-called on
        same-page reveals the way `record_inventory` now is for `Component`
        (see `GraphStore.record_text_content`'s docstring for why that's a
        deliberate, documented cut rather than an oversight).
        """
        for entry in text_content:
            path = entry.get("path")
            if not path:
                continue
            rect = entry.get("rect") or {}
            self.graph_store.record_text_content(
                self.site,
                page_key,
                path,
                tag=entry.get("tag", ""),
                text=entry.get("text", ""),
                visible=bool(entry.get("visible", True)),
                x=rect.get("x"),
                y=rect.get("y"),
                width=rect.get("width"),
                height=rect.get("height"),
            )

    def record_inventory(
        self, page_key: str, components: List[Dict[str, Any]], links: List[Dict[str, str]]
    ) -> None:
        """Full, unconditional component + link inventory for one discovery
        pass - every component gets a `record_component` call (idempotent,
        safe to call again on rediscovery) regardless of whether anything on
        it changed, mirroring the old `_record_page_inventory`'s
        "unconditional, not gated by any per-turn cap" discipline. Detected
        steppers/choice-sets get their structured facts attached via
        `record_component_options`, reusing `component_classifier.py`
        unchanged - the same deterministic, no-LLM classification the old
        catalog narration pass already relied on.
        """
        for comp in components:
            path = comp.get("path")
            if not path:
                continue
            rect = comp.get("rect") or {}
            self.graph_store.record_component(
                self.site,
                page_key,
                path,
                tag=comp.get("tag", ""),
                text=comp.get("text", ""),
                role=comp.get("role", ""),
                input_type=comp.get("input_type", ""),
                visible=bool(comp.get("visible", True)),
                layer=comp.get("discovery_layer", "semantic"),
                x=rect.get("x"),
                y=rect.get("y"),
                width=rect.get("width"),
                height=rect.get("height"),
                component_type=classify_component_type(comp),
            )

        for stepper in group_steppers(components):
            increment_path = stepper.get("increment_path")
            if increment_path:
                self.graph_store.record_component_options(
                    self.site, page_key, increment_path, json.dumps(stepper)
                )

        for name, members in group_choice_sets(components).items():
            option_summary = json.dumps(
                {
                    "group": name,
                    "options": [
                        {"path": m.get("path"), "text": m.get("text"), "selected": bool(m.get("selected"))}
                        for m in members
                    ],
                }
            )
            for member in members:
                path = member.get("path")
                if path:
                    self.graph_store.record_component_options(self.site, page_key, path, option_summary)

        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - see mechanical_loop's own identical filter
            if not href:
                continue
            self.graph_store.record_link(self.site, page_key, clean_url(href), link.get("text", ""))

    def record_interaction(self, page_key: str, path: str, action: str, value: str, resulting_url: str) -> None:
        """One call per *attempted* interaction (success or failure) - the
        component-level ledger's whole value is knowing what was tried, not
        just what worked. `resulting_url` is `""` for a failed interaction
        (nothing to report) or a same-page one (no navigation).
        """
        self.graph_store.record_component_interaction(
            self.site, page_key, path, action=action, value=value, resulting_url=resulting_url
        )

    def record_component_network(self, page_key: str, path: str, requests: List[Dict[str, Any]]) -> None:
        """One call per interaction that triggered >=1 meaningful (xhr/fetch)
        network request (see `src/crawlers/network_filter.py`) - the
        "request information" a real JS/SPA site's submit-like control needs,
        since it has no static `<form method/action>` to read instead.
        """
        self.graph_store.record_component_network(self.site, page_key, path, json.dumps(requests))

    def record_revealed_options(self, page_key: str, trigger_path: str, revealed: List[Dict[str, Any]]) -> None:
        """Attach a before/after-diff-detected set of newly revealed
        role="option"-family components (`component_classifier.
        find_revealed_options`) to the *trigger* component's `options` field
        - the click that opens a combobox/listbox doesn't carry its own
        choices in any single discovery snapshot, unlike every other field
        `record_component` refreshes; they only exist once the widget has
        actually been opened. Mirrors `group_steppers`/`group_choice_sets`'
        own `record_component_options` call in `record_inventory` above, but
        keyed by the specific interaction that produced it rather than a
        single-snapshot classification, since this fact genuinely isn't
        derivable from one snapshot alone.
        """
        payload = json.dumps({"trigger": trigger_path, "revealed_options": revealed})
        self.graph_store.record_component_options(self.site, page_key, trigger_path, payload)

    def record_navigation_edge(self, from_key: str, to_key: str, path: str, action: str) -> None:
        """Only called when an interaction's resulting URL differs from the
        page it was attempted on - a real navigation, not a same-page reveal.
        """
        self.graph_store.record_edge(self.site, from_key, to_key, component=path, action=action)

    def record_page_finished(self, page_key: str, component_count: int) -> None:
        """Called once a page's interaction pass completes *without* being
        cut short by a navigation (see `PageVisitResult.interrupted_by_navigation`)
        - an interrupted pass leaves the page genuinely incomplete, so it must
        stay `Pending` for its guaranteed follow-up pass, not be marked
        `Finished` prematurely.
        """
        self.graph_store.upsert_page(self.site, page_key, status="Finished", components=component_count)
