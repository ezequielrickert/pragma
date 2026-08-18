"""Which components are eligible for `PageVisitor`'s interaction frontier,
and why some get excluded even though they're still visible and
unvisited.
Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from ...content.component_matching import component_identity
from ..interaction_tracker import InteractionTracker


class Frontier:
    """Owns the per-page navigation-trigger and interacted-identity sets,
    and the eligibility rule built from them - replaces two near-identical
    list comprehensions that used to live inline in `PageVisitor.visit()`
    and `_transition_to_new_state`.
    Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#frontier
    """

    def __init__(self) -> None:
        # Identities proven to navigate away, site-wide - not page_key-keyed.
        # Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities
        self._navigation_trigger_identities: Set[tuple] = set()
        # page_key -> identities ever interacted with, regardless of path.
        # Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#_interacted_identities
        self._interacted_identities: Dict[str, Set[tuple]] = {}

    def _excluded_identities(self, page_key: str) -> Set[tuple]:
        return self._navigation_trigger_identities | self._interacted_identities.get(page_key, set())

    def is_excluded(self, page_key: str, component: Dict[str, Any]) -> bool:
        """Whether `component`'s content identity is a proven navigation
        trigger or already-interacted identity for `page_key` - the single-
        component check `_handle_same_page_reveal`'s append loop uses.
        Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#is_excluded
        """
        return component_identity(component) in self._excluded_identities(page_key)

    def eligible(
        self, page_key: str, components: List[Dict[str, Any]], tracker: InteractionTracker
    ) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Build a fresh interaction frontier from `components`: visible,
        not already interacted (per `tracker`), and not excluded (per
        `is_excluded`). Returns the frontier plus the set of paths it
        contains, since every caller needs both.
        Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#eligible
        """
        excluded = self._excluded_identities(page_key)
        frontier = [
            c for c in components
            if c.get("visible")
            and not tracker.is_interacted(page_key, c.get("path"))
            and component_identity(c) not in excluded
        ]
        seen_paths = {c.get("path") for c in frontier}
        return frontier, seen_paths

    def mark_navigation_trigger(self, component: Dict[str, Any]) -> None:
        """Remember `component`'s content identity as a proven one-way door,
        site-wide - not scoped to whichever page_key it was proven on.
        Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#mark_navigation_trigger
        """
        self._navigation_trigger_identities.add(component_identity(component))

    def mark_interacted_identity(self, page_key: str, component: Dict[str, Any]) -> None:
        """Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#mark_interacted_identity"""
        self._interacted_identities.setdefault(page_key, set()).add(component_identity(component))
