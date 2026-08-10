"""Consult-before-act seam for the mechanical crawl loop.
Details: docs/dev/crawlers/interaction_tracker.md#module
"""
from __future__ import annotations

from typing import Dict, Protocol, Set


class InteractionTracker(Protocol):
    """Consult-before-act seam; default is in-memory, Phase 3 swaps in a
    GraphStore-backed one. Details: docs/dev/crawlers/interaction_tracker.md#interactiontracker
    """

    def is_interacted(self, page_url: str, path: str) -> bool: ...

    def mark_interacted(self, page_url: str, path: str) -> None: ...

    def is_visited(self, page_url: str) -> bool: ...

    def mark_visited(self, page_url: str) -> None: ...


class InMemoryInteractionTracker:
    """Process-local `InteractionTracker` - lost on exit, Phase 2 default.
    Details: docs/dev/crawlers/interaction_tracker.md#inmemoryinteractiontracker
    """

    def __init__(self) -> None:
        self._interacted: Dict[str, Set[str]] = {}
        self._visited: Set[str] = set()

    def is_interacted(self, page_url: str, path: str) -> bool:
        return path in self._interacted.get(page_url, set())

    def mark_interacted(self, page_url: str, path: str) -> None:
        self._interacted.setdefault(page_url, set()).add(path)

    def is_visited(self, page_url: str) -> bool:
        return page_url in self._visited

    def mark_visited(self, page_url: str) -> None:
        self._visited.add(page_url)
