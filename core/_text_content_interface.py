"""Static-text-content half of the `GraphStore` contract - split out of
`interfaces.py` for the same file-size reason as
`_component_store_interface.py`. `_TextContentInterface` is combined into
the public `GraphStore` class in `interfaces.py` via multiple inheritance;
it is never instantiated on its own.

Must itself subclass `ABC`, not a plain class - see
`_component_store_interface.py`'s module docstring for why (a plain
mixin's `@abstractmethod`s are silently unenforced once composed).

Details: docs/dev/core/_text_content_interface.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class _TextContentInterface(ABC):
    """A separate node kind from Component, deliberately.
    Details: docs/dev/core/_text_content_interface.md#_textcontentinterface
    """

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
