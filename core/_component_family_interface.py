"""Inferred-component-family half of the `GraphStore` contract - split out
of `interfaces.py` for the same file-size reason as
`_component_store_interface.py`. `_ComponentFamilyInterface` is combined
into the public `GraphStore` class in `interfaces.py` via multiple
inheritance; it is never instantiated on its own.

Must itself subclass `ABC`, not a plain class - see
`_component_store_interface.py`'s module docstring for why (a plain
mixin's `@abstractmethod`s are silently unenforced once composed).

Details: docs/dev/core/_component_family_interface.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .data_contracts import ComponentFamily


class _ComponentFamilyInterface(ABC):
    """Details: docs/dev/core/_component_family_interface.md#_componentfamilyinterface"""

    # Inferred component families - a post-hoc, whole-site pass (not part
    # of the live per-page crawl write path); groups structurally/visually
    # similar Components into reusable patterns.
    #
    # This section used to also carry `apply_tag_labels`, a Neo4j-Browser-
    # specific visual affordance (per-tag node coloring) with no equivalent
    # once nothing renders the graph visually - removed with that backend.
    # Details: docs/dev/core/interfaces.md#component-families

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
            A list of `ComponentFamily` (see `data_contracts.py`'s own
            docstring for its fields), one per family - `[]` if
            `record_component_families` was never called for this site,
            or was last called with an empty list. Order is whatever the
            backend returns (both shipped backends return them in a
            deterministic but not otherwise meaningful order - see each
            one's own `get_component_families` docstring).
        Details: docs/dev/core/interfaces.md#get_component_families
        """
        raise NotImplementedError
