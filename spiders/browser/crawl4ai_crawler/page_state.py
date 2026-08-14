"""Assemble this project's PageState from one crawl4ai arun() result.
Details: docs/dev/spiders/browser/crawl4ai_crawler/page_state.md#module
"""
from __future__ import annotations

from typing import Any, Dict

from core.interfaces import PageState
from ...content.network_filter import filter_meaningful_requests


def resolved_url(result: Any, requested_url: str) -> str:
    """`result.url` is always the *requested* URL; use `redirected_url` instead.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/page_state.md#resolved_url
    """
    return getattr(result, "redirected_url", None) or result.url or requested_url


def build_page_state(result: Any, requested_url: str, data: Dict[str, Any]) -> PageState:
    """Assemble a `PageState` from one `arun()` result plus its stashed
    extraction dict - shared by every navigation method on `Crawl4AICrawler`
    rather than repeated per call site.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/page_state.md#build_page_state
    """
    return PageState(
        url=resolved_url(result, requested_url),
        title=data.get("title", ""),
        metadata=data.get("metadata", {}),
        components=data.get("components", []),
        links=data.get("links", []),
        description=data.get("description", ""),
        text_content=data.get("text_content", []),
        network_requests=filter_meaningful_requests(getattr(result, "network_requests", None) or []),
        accessibility_violations=data.get("accessibility_violations", []),
        pseudo_styles=data.get("pseudo_styles", []),
        tab_order=data.get("tab_order", []),
    )
