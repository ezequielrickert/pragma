"""Which components are eligible for `PageVisitor`'s interaction frontier,
and the exact-path canonicalization every reveal needs.
Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from ...content.component_matching import component_identity
from ..interaction_tracker import InteractionTracker


class Frontier:
    """Owns the interaction-eligibility rule and the per-page canonical-path
    map - replaces two near-identical list comprehensions that used to live
    inline in `PageVisitor.visit()` and `_transition_to_new_state`.

    Used to also track content-identity dedup (a component proven to
    navigate away, or already interacted with, excluded every other
    same-identity instance from ever being attempted - issue #214's
    "Conectar" case: every repeated card's connect/favorite/share button
    shares one identity by `tag`/`role`/`name`/`form`/`text`, so one
    instance's outcome silently decided every other card's for it,
    site-wide). Dropped in favor of exact-path tracking only
    (`InteractionTracker.is_interacted`) - every distinct DOM node gets its
    own real attempt now, at the cost of the site-wide nav-menu dedup this
    used to buy (confirmed live on austral.edu.ar: a persistent nav menu
    present on every page was being fully re-explored per page, dominating
    real crawl time on a site whose nav items number in the hundreds -
    `tests/test_mechanical_loop.py::test_site_wide_nav_link_is_reattempted_per_page`
    now documents that traded-off cost instead of guarding against it).
    Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#frontier
    """

    def __init__(self) -> None:
        # page_key -> {identity: the path it was first recorded under}.
        # Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#_canonical_paths
        self._canonical_paths: Dict[str, Dict[tuple, str]] = {}

    def eligible(
        self, page_key: str, components: List[Dict[str, Any]], tracker: InteractionTracker
    ) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Build a fresh interaction frontier from `components`: visible and
        not already interacted (per `tracker`, exact-path). Returns the
        frontier plus the set of paths it contains, since every caller
        needs both.
        Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#eligible
        """
        frontier = [
            c for c in components
            if c.get("visible") and not tracker.is_interacted(page_key, c.get("path"))
        ]
        seen_paths = {c.get("path") for c in frontier}
        return frontier, seen_paths

    def canonicalize_inventory(
        self, page_key: str, components: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """`components`, each pinned to the `path` its content identity was
        first recorded under on this page - what every `record_inventory`
        call should persist instead of a component's own live `path`.

        A same-page reveal can compute a different `nth-of-type`-derived
        path for a physical instance this page already recorded, even once
        `component_identity()` itself is drift-immune (#170): pinning the
        path here means database/ladybug/component.py's `path`-keyed
        `HAS_COMPONENT` `MERGE` still only ever sees one edge for that
        instance, instead of minting a spurious extra one per drifted
        reveal. Deliberately doesn't touch `component["path"]` itself -
        callers still need the live path to target the real element for
        interaction; only the copies handed to the graph store are pinned.

        Purely a graph-store bookkeeping concern, unlike the interaction-
        skipping identity dedup this module used to also do (see the class
        docstring) - two different professionals' otherwise-identical
        "Conectar" buttons still get pinned to their own separate paths
        here (distinct DOM instances, distinct `Component` nodes); this
        only re-stabilizes one instance's path across reveals of *itself*.
        Details: docs/dev/spiders/orchestration/page_visitor/frontier.md#canonicalize_inventory
        """
        canonical = self._canonical_paths.setdefault(page_key, {})
        return [
            {**component, "path": canonical.setdefault(component_identity(component), component.get("path", ""))}
            for component in components
        ]
