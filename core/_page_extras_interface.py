"""Page-level "extras" half of the `GraphStore` contract - network loads,
stylesheets, and `<meta>` tag capture. Split out of `interfaces.py` for the
same file-size reason as `_component_store_interface.py`; mirrors
`_DuckDBPageExtrasMixin`'s split on the concrete side.

`_PageExtrasInterface` is combined into the public `GraphStore` class in
`interfaces.py` via multiple inheritance; it is never instantiated on its
own.

Must itself subclass `ABC`, not a plain class - see
`_component_store_interface.py`'s module docstring for why (a plain
mixin's `@abstractmethod`s are silently unenforced once composed).

Details: docs/dev/core/_page_extras_interface.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class _PageExtrasInterface(ABC):
    """Details: docs/dev/core/_page_extras_interface.md#_pageextrasinterface"""

    @abstractmethod
    def record_page_network(self, site: str, page_url: str, requests: List[Dict[str, Any]]) -> None:
        """Append one batch of requests the page's own *load* fired, as
        opposed to `record_component_network`'s per-interaction batches.

        Args:
            site: which site this page belongs to.
            page_url: the page whose load produced these requests.
            requests: a list of `network_filter.filter_meaningful_requests`-shaped dicts.

        Returns:
            None - a write-only side effect.
        Details: docs/dev/core/interfaces.md#record_page_network
        """
        raise NotImplementedError

    @abstractmethod
    def get_page_network_ledger(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        """`{page_url: [request, ...]}` for every page of `site` whose load
        fired at least one. Pages that fired none are absent, not present
        with an empty list.
        Details: docs/dev/core/interfaces.md#get_page_network_ledger
        """
        raise NotImplementedError

    def record_stylesheets(self, site: str, page_url: str, stylesheets: List[Dict[str, Any]]) -> None:
        """Replace one page's same-origin CSS captures.

        Args:
            site: which site this page belongs to.
            page_url: the page these stylesheets were captured on.
            stylesheets: `[{"href", "accessible", "excerpt", "byte_length",
                "hash"}, ...]` - `excerpt`/`byte_length`/`hash` come from
                `payload_capture.truncate_and_hash`, same shape a network
                payload's capture produces. No redaction: CSS is public
                presentational code, not a credential-bearing payload.

        Returns:
            None - a write-only side effect. Replace, not append: a page
            revisited later gets its stylesheet capture refreshed, not
            stacked with the previous visit's.

        Not abstract - a backend with no use for stylesheet capture can
        ignore this, same reasoning as `record_page_metadata` below.
        Details: docs/dev/core/interfaces.md#record_stylesheets
        """

    def get_stylesheets(self, site: str) -> Dict[str, List[Dict[str, Any]]]:
        """`{page_url: [stylesheet, ...]}` for every page with a captured
        stylesheet. `{}` for a backend/site where `record_stylesheets` was
        never called.
        Details: docs/dev/core/interfaces.md#get_stylesheets
        """
        return {}

    def record_page_metadata(self, site: str, page_url: str, metadata: Dict[str, str]) -> None:
        """Store a page's `<meta>` tags.

        Extracted by `run_extraction` on every navigation since long before
        this method existed, and thrown away every time. They carry the
        description, viewport, and any Open Graph or framework markers a
        page declares about itself - the site's own account of what it is.
        Details: docs/dev/core/interfaces.md#record_page_metadata
        """

    def get_page_metadata(self, site: str) -> Dict[str, Dict[str, str]]:
        """`{page_url: {meta_name: content}}` for pages that declared any.
        Details: docs/dev/core/interfaces.md#get_page_metadata
        """
        return {}
