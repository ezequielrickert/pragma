"""Inferred-API-endpoint half of the `GraphStore` contract - split out of
`interfaces.py` for the same file-size reason as
`_component_store_interface.py`. `_RequestFamilyInterface` is combined
into the public `GraphStore` class in `interfaces.py` via multiple
inheritance; it is never instantiated on its own.

Must itself subclass `ABC`, not a plain class - see
`_component_store_interface.py`'s module docstring for why (a plain
mixin's `@abstractmethod`s are silently unenforced once composed).

Details: docs/dev/core/_request_family_interface.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .data_contracts import InferredRequest


class _RequestFamilyInterface(ABC):
    """Details: docs/dev/core/_request_family_interface.md#_requestfamilyinterface"""

    # Same "post-hoc, whole-site pass" shape as component families,
    # computed by generators/request_family.py from network requests
    # already captured on Component nodes.
    # Details: docs/dev/core/interfaces.md#inferred-requests

    @abstractmethod
    def record_inferred_requests(self, site: str, requests: List[InferredRequest]) -> None:
        """Replace `site`'s entire inferred-request structure with
        `requests` - a from-scratch rebuild, same "cluster membership
        isn't guaranteed stable across runs" reasoning as
        `record_component_families`.

        Args:
            site: which site's inferred requests to replace.
            requests: the complete new set, typically the direct output
                of `request_family.build_inferred_requests`. `[]` clears
                every inferred request for `site`.

        Returns:
            None - a write-only side effect.
        Details: docs/dev/core/interfaces.md#record_inferred_requests
        """
        raise NotImplementedError

    @abstractmethod
    def get_inferred_requests(self, site: str) -> List[InferredRequest]:
        """Every inferred API endpoint currently recorded for `site`.

        Args:
            site: which site's inferred requests to read.

        Returns:
            A list of `InferredRequest`, `[]` if `record_inferred_requests`
            was never called for this site, or was last called with an
            empty list.
        Details: docs/dev/core/interfaces.md#get_inferred_requests
        """
        raise NotImplementedError
