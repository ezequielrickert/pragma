"""Core interfaces and data contracts for the Pragma micro-kernel.
Details: docs/dev/core/interfaces.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PageState:
    """Normalized snapshot of a crawled page (the Crawler -> orchestrator contract)."""

    url: str
    title: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    components: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    # Short (~300 char) page summary; "" if the backend doesn't extract it.
    # Details: docs/dev/core/interfaces.md#pagestatedescription
    description: str = ""
    # Meaningful (xhr/fetch) requests triggered by the interaction, if any.
    # Details: docs/dev/core/interfaces.md#pagestatenetwork_requests
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    # Non-interactive prose, captured once per page visit alongside components.
    # Details: docs/dev/core/interfaces.md#pagestatetext_content
    text_content: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ComponentFacts:
    """DOM-attribute and computed-style facts about a discovered element,
    beyond the core identity/geometry `record_component` already took as
    named params. Grouped into one object rather than growing that method's
    own argument list further - see docs/dev/core/interfaces.md#componentfacts
    for which facts are here and, notably, which one (`value`) isn't and why.
    """

    css_class: str = ""
    element_id: str = ""
    href: str = ""
    placeholder: str = ""
    label: str = ""
    name: str = ""
    disabled: bool = False
    required: bool = False
    form: str = ""
    color: str = ""
    background_color: str = ""
    font_size: str = ""
    font_weight: str = ""
    display: str = ""
    position: str = ""


@dataclass(frozen=True)
class ComponentFamily:
    """One inferred reusable-component cluster (a "Button" pattern, a
    "combobox" pattern, ...) - a post-hoc, whole-site grouping of already-
    discovered Components by structural/visual similarity, computed by
    `src/generators/component_family.py::build_component_families` (that
    module's own docstring has the full algorithm - bucketed by `(tag,
    component_type)`, then clustered within each bucket by CSS-class
    similarity). Lives here (not in `generators/`) so `GraphStore` - a
    `core` module - can reference the type without `core` depending on
    `generators`, the reverse of this project's normal layering.

    Frozen + tuple fields (not list) so a `ComponentFamily` is hashable
    and safely comparable by value - callers (tests, in particular) can
    put one in a `set` or compare two family lists with plain `==`.

    Fields:
        tag: the raw HTML tag every member shares, e.g. `"button"`,
            `"input"`, `"a"`. See `component_family.label_for_tag` for
            how this becomes a Neo4j node label (`"button"` -> `Button`,
            `"a"` -> `Link`, etc.) - a related but separate mechanism
            from family grouping itself.
        component_type: the human-readable role label every member
            shares, e.g. `"button"`, `"submit button"`, `"checkbox"`,
            `"combobox (searchable dropdown)"` - the same value
            `component_classifier.classify_component_type` already
            computed for each component at crawl time. Two components
            with the same `tag` but different `component_type` are never
            in the same family, regardless of how similar their classes
            are.
        common_classes: the CSS classes *every* member has in common -
            sorted for a deterministic, human-readable summary of what
            the family visually shares (e.g. `("btn", "rounded")` for a
            primary/secondary button pair that differs only by its
            color-modifier class, which is correctly excluded here since
            not every member has it).
        member_paths: one `(page_url, path)` pair per member component -
            together, the two fields are exactly the identity key
            (`site` is implied by whichever call this came from)
            `GraphStore.record_component`/`get_component_states` use for
            a single `Component` node. Sorted for a deterministic order.
        purpose: one-sentence, human-readable description of what this
            pattern is typically used for (e.g. "confirms or submits an
            action"), or `""` if it was never narrated. `build_component_
            families` itself never sets this (clustering is pure/no-LLM,
            per that module's own docstring) - it's filled in afterward
            by `component_family_narrator.narrate_family_purposes`, an
            explicitly separate, impure step that needs an `Agent`.
    """

    tag: str
    component_type: str
    common_classes: Tuple[str, ...]
    member_paths: Tuple[Tuple[str, str], ...]
    purpose: str = ""


class Agent(ABC):
    """Interface for AI agent backends."""

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Return text generated by an LLM or agent backend."""
        raise NotImplementedError


class GraphStore(ABC):
    """Interface for the crawl graph's persistence/query backend, scoped per site.
    Details: docs/dev/core/interfaces.md#graphstore
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection and idempotently ensure schema exists."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release the connection. Safe to call even if never connected."""
        raise NotImplementedError

    @abstractmethod
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
        """Create or update a page node for `site`; never clobbers Finished with Pending.
        Details: docs/dev/core/interfaces.md#upsert_page
        """
        raise NotImplementedError

    @abstractmethod
    def get_page_descriptions(self, site: str) -> Dict[str, str]:
        """{url: description} for every page of `site` that has one recorded."""
        raise NotImplementedError

    @abstractmethod
    def get_page_titles(self, site: str) -> Dict[str, str]:
        """{url: title} for every page of `site` that has one recorded.
        Details: docs/dev/core/interfaces.md#get_page_titles
        """
        raise NotImplementedError

    @abstractmethod
    def is_visited(self, site: str, url: str) -> bool:
        """Whether this page is a Finished node in the graph for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_pending(self, site: str, limit: Optional[int] = None) -> List[str]:
        """Up to `limit` Pending page urls for `site`, sorted ascending. Unbounded if limit is None."""
        raise NotImplementedError

    @abstractmethod
    def get_page_label(self, site: str, url: str) -> Optional[str]:
        """The link-text label recorded for a page, if any."""
        raise NotImplementedError

    @abstractmethod
    def record_link(self, site: str, from_url: str, to_url: str, label: str) -> None:
        """Record a discovered link and its visible text, distinct from a taken navigation.
        Details: docs/dev/core/interfaces.md#record_link
        """
        raise NotImplementedError

    def record_links(self, site: str, from_url: str, links: List[Dict[str, str]]) -> None:
        """Batched `record_link`: each item is `{"to_url", "label"}`. Not
        abstract - the default loops the per-item call, so only a backend
        that can do better (e.g. one round-trip covering the whole page's
        links) needs to override it.
        Details: docs/dev/core/interfaces.md#record_links
        """
        for item in links:
            self.record_link(site, from_url, item["to_url"], item.get("label", ""))

    @abstractmethod
    def get_link_label(self, site: str, from_url: str, to_url: str) -> Optional[str]:
        """The label of a specific from->to link discovery, if one was ever recorded."""
        raise NotImplementedError

    @abstractmethod
    def record_edge(self, site: str, from_url: str, to_url: str, component: str, action: str) -> None:
        """Record a successful navigation from `from_url` to `to_url` for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_edges(self, site: str) -> List[Dict[str, str]]:
        """All recorded edges for `site`, each {"from", "component", "action", "to"}, in insertion order."""
        raise NotImplementedError

    @abstractmethod
    def get_progress_table_rows(self, site: str) -> List[Dict[str, Any]]:
        """All page rows for `site` as {"url", "status", "components", "label"}, sorted."""
        raise NotImplementedError

    @abstractmethod
    def count_visited(self, site: str) -> Tuple[int, int]:
        """(finished_count, total_count) of pages tracked for `site`."""
        raise NotImplementedError

    @abstractmethod
    def get_loop_signals(self, site: str, url: str) -> List[Dict[str, str]]:
        """Distinct {"component", "from"} pairs of edges already leading into `url`."""
        raise NotImplementedError

    @abstractmethod
    def clear_site(self, site: str) -> None:
        """Delete every page/edge/link/component tracked for `site`.
        Details: docs/dev/core/interfaces.md#clear_site
        """
        raise NotImplementedError

    # Component-level frontier: per-element interacted state, keyed by
    # (site, page_url, path). Details: docs/dev/core/interfaces.md#component-level-frontier

    @abstractmethod
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
        """Create or refresh a Component node's descriptive fields only.
        `facts` defaults to an empty `ComponentFacts()` when omitted, same as
        every other optional field here defaulting to its own "unknown" value.
        Details: docs/dev/core/interfaces.md#record_component
        """
        raise NotImplementedError

    def record_components(self, site: str, page_url: str, components: List[Dict[str, Any]]) -> None:
        """Batched `record_component`: each item is a kwargs dict matching
        `record_component`'s own signature (minus `site`/`page_url`). Not
        abstract - the default loops the per-item call; a backend can
        override it to write a whole discovery pass's worth of components
        in one round-trip instead of one per component.
        Details: docs/dev/core/interfaces.md#record_components
        """
        for item in components:
            self.record_component(site, page_url, **item)

    @abstractmethod
    def record_component_options(
        self, site: str, page_url: str, path: str, options: str, option_labels: Optional[List[str]] = None
    ) -> None:
        """Overwrite a Component's JSON-encoded `options` field; auto-creates the node.

        Args:
            site: which site this component belongs to.
            page_url: the component's own page key.
            path: the component's own CSS selector path.
            options: raw JSON-encoded blob in one of the shapes
                `component_classifier.describe_options` knows how to
                parse (stepper / choice_group / revealed_options) -
                stored as-is, for callers (`choice_text_by_path`,
                `describe_options` itself) that need the full structure
                (per-choice `path`, which member redirected where, etc.).
            option_labels: the same data, already reduced to plain
                display strings by `component_classifier.
                format_option_choices` (e.g. `["Mi Gusto (selected)",
                "Solo Empanadas", ...]`) - computed by the caller
                (`GraphStoreSink`), not by this method, so `options`
                stays the single source of truth and this is purely a
                convenience projection of it. `None`/omitted stores `[]`,
                not an error - not every `record_component_options` call
                site necessarily has this computed yet.

        Returns:
            None.
        Details: docs/dev/core/interfaces.md#record_component_options
        """
        raise NotImplementedError

    @abstractmethod
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
        """Mark a component as interacted with and append one interaction record.
        `source_path` names the specific member that acted when `path` is a
        consolidated choice-group/dropdown's representative node rather than
        the member itself - "" when they're the same (the ordinary case).
        Details: docs/dev/core/interfaces.md#record_component_interaction
        """
        raise NotImplementedError

    @abstractmethod
    def record_component_network(self, site: str, page_url: str, path: str, requests_json: str) -> None:
        """Append one JSON-encoded batch of meaningful network requests to a Component.
        Details: docs/dev/core/interfaces.md#record_component_network
        """
        raise NotImplementedError

    @abstractmethod
    def get_component_states(self, site: str, page_url: str) -> Dict[str, Dict[str, Any]]:
        """All known components for one page, one query per page visit.
        Details: docs/dev/core/interfaces.md#get_component_states
        """
        raise NotImplementedError

    @abstractmethod
    def count_unexplored_components(self, site: str, semantic_only: bool = True) -> Tuple[int, int]:
        """(unexplored_count, total_count) of components tracked across all of `site`.
        Details: docs/dev/core/interfaces.md#count_unexplored_components
        """
        raise NotImplementedError

    @abstractmethod
    def get_pages_with_unexplored_components(
        self, site: str, limit: Optional[int] = None, semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        """[{"url", "unexplored_count"}] for pages with >=1 unexplored component, sorted descending."""
        raise NotImplementedError

    @abstractmethod
    def page_has_unexplored_components(self, site: str, url: str, semantic_only: bool = True) -> bool:
        """Whether `url` has at least one un-interacted-with component tracked."""
        raise NotImplementedError

    @abstractmethod
    def get_component_ledger(self, site: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Full per-component interaction/options/network-request record for all of `site`.
        Details: docs/dev/core/interfaces.md#get_component_ledger
        """
        raise NotImplementedError

    # Inferred component families - a post-hoc, whole-site pass (not part
    # of the live per-page crawl write path); groups structurally/visually
    # similar Components into reusable patterns.
    # Details: docs/dev/core/interfaces.md#component-families

    def apply_tag_labels(self, site: str, tag_labels: Dict[str, str]) -> None:
        """Give every Component a label matching its own HTML tag (e.g.
        `:Button`, `:Input`, `:Link`) wherever `tag_labels` names one for
        it - a Neo4j-Browser-specific visual affordance (node color
        follows label) with no equivalent in a backend with no browser to
        color.

        Args:
            site: which site's components to label - same scoping every
                other `GraphStore` method uses.
            tag_labels: `{raw_tag: label_name}`, e.g. `{"button":
                "Button", "input": "Input", "a": "Link"}`. Fully computed
                by the caller (`tags_with_multiple_instances` +
                `label_for_tag`, both in `component_family.py`) - this
                method does no thresholding (deciding which tags are
                "common enough") or naming (deciding what a tag's label
                should be) of its own, so both decisions live in exactly
                one place rather than being duplicated between a
                `GraphStore` backend and the module that calls it. Only
                the tags present as keys get a label added; any Component
                whose tag isn't in this dict is left with just its base
                `:Component` label.

        Returns:
            None - a write-only side effect (adds Neo4j labels). Not
            abstract: the default implementation here is a no-op, and
            only `Neo4jGraphStore` overrides it with a real
            implementation - there's no equivalent concept for a backend
            with no browser to color (e.g. `InMemoryGraphStore`).
        Details: docs/dev/core/interfaces.md#apply_tag_labels
        """

    @abstractmethod
    def record_component_families(self, site: str, families: List[ComponentFamily]) -> None:
        """Replace `site`'s entire inferred-family structure with
        `families` - a from-scratch rebuild (any families from a previous
        run are cleared first), since cluster membership isn't guaranteed
        to stay the same between runs as the underlying components change
        (a component that was a singleton last run might gain a sibling
        this run, or vice versa).

        Args:
            site: which site's families to replace.
            families: the complete new set, typically the direct output
                of `component_family.build_component_families` - passing
                `[]` clears every family for `site` without recording any
                new ones (used, for example, by a re-run that finds no
                families at all this time).

        Returns:
            None - a write-only side effect.
        Details: docs/dev/core/interfaces.md#record_component_families
        """
        raise NotImplementedError

    @abstractmethod
    def get_component_families(self, site: str) -> List[ComponentFamily]:
        """Every inferred family currently recorded for `site`.

        Args:
            site: which site's families to read.

        Returns:
            A list of `ComponentFamily` (see `src/core/interfaces.py`'s
            own docstring for its fields), one per family - `[]` if
            `record_component_families` was never called for this site,
            or was last called with an empty list. Order is whatever the
            backend returns (both shipped backends return them in a
            deterministic but not otherwise meaningful order - see each
            one's own `get_component_families` docstring).
        Details: docs/dev/core/interfaces.md#get_component_families
        """
        raise NotImplementedError

    # Static text content: a separate node kind from Component, deliberately.
    # Details: docs/dev/core/interfaces.md#static-text-content

    @abstractmethod
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
        """Create or refresh a text-content record; called once per page visit.
        Details: docs/dev/core/interfaces.md#record_text_content
        """
        raise NotImplementedError

    def record_text_contents(self, site: str, page_url: str, entries: List[Dict[str, Any]]) -> None:
        """Batched `record_text_content`: each item is a kwargs dict matching
        `record_text_content`'s own signature (minus `site`/`page_url`). Not
        abstract - see `record_components` for why.
        Details: docs/dev/core/interfaces.md#record_text_contents
        """
        for item in entries:
            self.record_text_content(site, page_url, **item)

    @abstractmethod
    def get_text_content_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        """{page_url: [{"path", "tag", "text", "visible", "x", "y", "width", "height"}, ...]}."""
        raise NotImplementedError
