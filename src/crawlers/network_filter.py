"""Pure reduction of crawl4ai's raw network events to the ones worth keeping.
Details: docs/dev/crawlers/network_filter.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# xhr/fetch only - not images/fonts/stylesheets/documents/websockets.
# Details: docs/dev/crawlers/network_filter.md#_meaningful_resource_types
_MEANINGFUL_RESOURCE_TYPES = {"xhr", "fetch"}


def filter_meaningful_requests(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce one `arun()` call's `result.network_requests` to the meaningful subset.
    Details: docs/dev/crawlers/network_filter.md#filter_meaningful_requests
    """
    if not raw_events:
        return []

    statuses_by_url: Dict[str, Optional[int]] = {}
    failures_by_url: Dict[str, str] = {}
    for event in raw_events:
        event_type = event.get("event_type")
        if event_type == "response":
            statuses_by_url[event.get("url")] = event.get("status")
        elif event_type == "response_capture_error":
            # Body unreadable but the response did arrive - no status either way.
            statuses_by_url.setdefault(event.get("url"), None)
        elif event_type == "request_failed":
            failures_by_url[event.get("url")] = event.get("failure_text") or "request failed"

    results = []
    for event in raw_events:
        if event.get("event_type") != "request":
            continue
        if event.get("resource_type") not in _MEANINGFUL_RESOURCE_TYPES:
            continue
        url = event.get("url")
        failed = url in failures_by_url
        results.append(
            {
                "method": event.get("method", ""),
                "url": url,
                "resource_type": event.get("resource_type", ""),
                "status": statuses_by_url.get(url),
                "failed": failed,
                "failure_text": failures_by_url.get(url) if failed else None,
            }
        )
    return results
