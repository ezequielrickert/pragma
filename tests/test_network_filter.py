"""Unit tests for filter_meaningful_requests (src/crawlers/network_filter.py) -
pure function, hand-built event dicts, no browser/crawl4ai dependency."""
from src.crawlers.network_filter import filter_meaningful_requests


def test_empty_or_none_input_returns_empty():
    assert filter_meaningful_requests([]) == []
    assert filter_meaningful_requests(None) == []


def test_image_and_font_requests_are_dropped():
    events = [
        {"event_type": "request", "url": "/logo.png", "method": "GET", "resource_type": "image"},
        {"event_type": "request", "url": "/font.woff2", "method": "GET", "resource_type": "font"},
        {"event_type": "request", "url": "/style.css", "method": "GET", "resource_type": "stylesheet"},
        {"event_type": "request", "url": "/page.html", "method": "GET", "resource_type": "document"},
    ]
    assert filter_meaningful_requests(events) == []


def test_xhr_and_fetch_requests_are_kept_with_joined_status():
    events = [
        {"event_type": "request", "url": "/api/ping", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response", "url": "/api/ping", "status": 200},
        {"event_type": "request", "url": "/api/legacy", "method": "POST", "resource_type": "xhr"},
        {"event_type": "response", "url": "/api/legacy", "status": 201},
    ]
    result = filter_meaningful_requests(events)
    assert len(result) == 2
    ping = next(r for r in result if r["url"] == "/api/ping")
    assert ping == {
        "method": "GET", "url": "/api/ping", "resource_type": "fetch",
        "status": 200, "failed": False, "failure_text": None,
    }
    legacy = next(r for r in result if r["url"] == "/api/legacy")
    assert legacy["status"] == 201
    assert legacy["method"] == "POST"


def test_response_capture_error_leaves_status_none_not_a_crash():
    events = [
        {"event_type": "request", "url": "/api/stream", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response_capture_error", "url": "/api/stream", "error": "could not decode body"},
    ]
    result = filter_meaningful_requests(events)
    assert len(result) == 1
    assert result[0]["status"] is None
    assert result[0]["failed"] is False


def test_request_failed_is_surfaced():
    events = [
        {"event_type": "request", "url": "/api/down", "method": "GET", "resource_type": "xhr"},
        {"event_type": "request_failed", "url": "/api/down", "failure_text": "net::ERR_CONNECTION_REFUSED"},
    ]
    result = filter_meaningful_requests(events)
    assert len(result) == 1
    assert result[0]["failed"] is True
    assert result[0]["failure_text"] == "net::ERR_CONNECTION_REFUSED"
    assert result[0]["status"] is None


def test_response_body_text_is_never_present_in_output():
    """Deliberate: response body text can be arbitrarily large and may
    contain secrets/PII - must never reach the filtered output."""
    events = [
        {"event_type": "request", "url": "/api/ping", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response", "url": "/api/ping", "status": 200, "body": {"text": "super secret payload"}},
    ]
    result = filter_meaningful_requests(events)
    assert "body" not in result[0]
    assert "secret" not in str(result[0])


def test_capture_error_event_types_never_match_the_keep_filter():
    """request_capture_error/request_failed_capture_error carry no
    resource_type at all - they must never spuriously pass the xhr/fetch
    filter (they're not "request" event_type in the first place)."""
    events = [
        {"event_type": "request_capture_error", "url": "/api/x", "error": "boom"},
        {"event_type": "request_failed_capture_error", "url": "/api/y", "error": "boom"},
    ]
    assert filter_meaningful_requests(events) == []
