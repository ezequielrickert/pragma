"""Component-CRUD half of the `GraphStore` contract - split out of
`interfaces.py` once that file crossed the file-size SPLIT threshold
(626 lines) growing by roughly one new capability per storage-migration
phase. Mirrors the split every concrete backend already uses
(`_DuckDBComponentMixin`, and the retired Neo4j backend's
`_Neo4jComponentMixin` before it) - the interface itself had never had
the same treatment.

`_ComponentStoreInterface` is combined into the public `GraphStore` class
in `interfaces.py` via multiple inheritance; it is never instantiated on
its own.

Must itself subclass `ABC` (not a plain class) - Python's `ABCMeta` only
computes a composed class's `__abstractmethods__` by reading each base's
*own* `__abstractmethods__` attribute, which only exists on classes that
went through `ABCMeta.__new__` themselves. A plain mixin's `@abstractmethod`
methods are silently unenforced once composed into `GraphStore`: a backend
missing one would still instantiate, and only fail with `NotImplementedError`
the first time that specific method was actually called - confirmed live
while building this split, not a theoretical concern.

Details: docs/dev/core/_component_store_interface.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from .data_contracts import ComponentFacts, VisitStep


class _ComponentStoreInterface(ABC):
    """Details: docs/dev/core/_component_store_interface.md#_componentstoreinterface"""

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
        self, site: str, page_url: str, path: str, options: Dict[str, Any], option_labels: Optional[List[str]] = None
    ) -> None:
        """Overwrite a Component's `options` field; auto-creates the node.

        Args:
            site: which site this component belongs to.
            page_url: the component's own page key.
            path: the component's own CSS selector path.
            options: a plain dict in one of the shapes
                `component_classifier.describe_options` knows how to
                parse (stepper / choice_group / revealed_options) -
                a genuine union type (each kind's keys differ), so it
                stays an opaque dict rather than a typed dataclass;
                stored as-is (JSON-encoded internally by whichever
                backend needs a string column/property - never a
                caller-facing concern), for callers (`choice_text_by_path`,
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
        step: Optional["VisitStep"] = None,
    ) -> None:
        """Mark a component as interacted with and append one interaction record.
        `step` places this interaction in its visit's sequence - see
        `VisitStep`. `None` records it unordered, which is what every
        caller predating the trace work does.
        `source_path` names the specific member that acted when `path` is a
        consolidated choice-group/dropdown's representative node rather than
        the member itself - "" when they're the same (the ordinary case).
        Details: docs/dev/core/interfaces.md#record_component_interaction
        """
        raise NotImplementedError

    @abstractmethod
    def record_component_network(self, site: str, page_url: str, path: str, requests: List[Dict[str, Any]]) -> None:
        """Append one batch of meaningful network requests to a Component.
        Each dict is `network_filter.filter_meaningful_requests`-shaped -
        stored as-is; JSON encoding, where a backend's storage needs it, is
        that backend's own internal concern, never the caller's.
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
