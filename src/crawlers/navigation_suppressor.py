"""Keeps one live page rendered for the whole of its interaction pass by
aborting the top-level navigations its own components trigger.
Details: docs/dev/crawlers/navigation_suppressor.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Playwright's resource_type for a top-level or iframe document load - the
# only kind of request that can take the session off the page being worked
# on. Details: docs/dev/crawlers/navigation_suppressor.md#_document_resource_type
_DOCUMENT_RESOURCE_TYPE = "document"

# Marker attribute set on the Playwright page while an interaction is in
# flight. Details: docs/dev/crawlers/navigation_suppressor.md#_armed_attribute
_ARMED_ATTRIBUTE = "_pragma_suppressing_session"


class NavigationSuppressor:
    """Decides which requests to abort, and remembers where each aborted one
    was headed so the crawl can queue that destination as a page of its own.
    Details: docs/dev/crawlers/navigation_suppressor.md#navigationsuppressor
    """

    def __init__(self) -> None:
        # session_id -> [{"url", "method"}], drained by take().
        # Details: docs/dev/crawlers/navigation_suppressor.md#_by_session
        self._by_session: Dict[str, List[Dict[str, str]]] = {}

    @staticmethod
    def arm(page: Any, session_id: str) -> None:
        """Start suppressing on `page`; every abort is attributed to `session_id`.
        Details: docs/dev/crawlers/navigation_suppressor.md#arm
        """
        setattr(page, _ARMED_ATTRIBUTE, session_id)

    @staticmethod
    def disarm(page: Any) -> None:
        """Let `page` navigate freely again - the state a real `goto()` needs.
        Details: docs/dev/crawlers/navigation_suppressor.md#disarm
        """
        setattr(page, _ARMED_ATTRIBUTE, None)

    def intercept(self, page: Any, request: Any) -> bool:
        """Record `request` as a suppressed navigation and report whether the
        caller must abort it.
        Details: docs/dev/crawlers/navigation_suppressor.md#intercept
        """
        session_id: Optional[str] = getattr(page, _ARMED_ATTRIBUTE, None)
        if session_id is None:
            return False
        if request.resource_type != _DOCUMENT_RESOURCE_TYPE:
            return False
        if not request.is_navigation_request():
            return False
        if not self._is_top_level(page, request):
            return False
        self._by_session.setdefault(session_id, []).append(
            {"url": request.url, "method": (request.method or "GET").upper()}
        )
        return True

    @staticmethod
    def _is_top_level(page: Any, request: Any) -> bool:
        """Whether `request` would replace the whole page rather than reload
        an iframe inside it - an iframe re-navigating leaves the page (and
        every selector built against it) perfectly intact, so suppressing it
        would cost real coverage for no benefit.
        Details: docs/dev/crawlers/navigation_suppressor.md#_is_top_level
        """
        try:
            return request.frame is page.main_frame
        except Exception:
            # Service-worker-issued requests have no frame at all; those can't
            # navigate the page either. Details: .../navigation_suppressor.md#_is_top_level
            return False

    def take(self, session_id: str) -> List[Dict[str, str]]:
        """Hand over and forget everything suppressed for `session_id` so far.
        Details: docs/dev/crawlers/navigation_suppressor.md#take
        """
        return self._by_session.pop(session_id, [])
