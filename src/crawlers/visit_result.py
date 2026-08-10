"""Data returned by one `MechanicalCrawler` page visit.
Details: docs/dev/crawlers/visit_result.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ComponentInteraction:
    page_url: str
    path: str
    action: str  # "click" | "fill"
    value: str = ""
    resulting_url: str = ""
    error: Optional[str] = None
    # Frontier item dropped by a stale-selector remap, not a real attempt.
    # Details: docs/dev/crawlers/visit_result.md#componentinteractionstale
    stale: bool = False


@dataclass
class PageVisitResult:
    url: str
    components_discovered: int
    interactions: List[ComponentInteraction] = field(default_factory=list)
    links_discovered: int = 0
    budget_exhausted_with_frontier_remaining: bool = False
    # The literal, redirect-resolved URL this visit actually landed on.
    # Details: docs/dev/crawlers/visit_result.md#pagevisitresultresolved_url
    resolved_url: str = ""
    # Set when a click/fill mid-pass navigated away before the frontier drained.
    # Details: docs/dev/crawlers/visit_result.md#pagevisitresultinterrupted_by_navigation
    interrupted_by_navigation: bool = False
    # Every in-page SPA state this pass switched onto, in order.
    # Details: docs/dev/crawlers/visit_result.md#pagevisitresultstate_transitions
    state_transitions: List[str] = field(default_factory=list)
