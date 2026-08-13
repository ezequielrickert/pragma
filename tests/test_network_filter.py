"""Unit tests for filter_meaningful_requests (src/crawlers/network_filter.py) -
pure function, hand-built event dicts, no browser/crawl4ai dependency."""
import json

from src.crawlers.network_filter import _json_shape, _shape_of_json_text, filter_meaningful_requests


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
        "body_shape": "", "response_shape": "", "latency_ms": None,
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


def test_json_shape_replaces_every_value_with_its_type_name():
    shape = _json_shape({"share_token": "abc123", "count": 3, "active": True, "note": None})
    assert shape == {"share_token": "string", "count": "number", "active": "boolean", "note": "null"}


def test_json_shape_nested_objects_and_arrays():
    shape = _json_shape({"items": [{"id": "x1", "qty": 2}], "meta": {"page": 1}})
    assert shape == {"items": [{"id": "string", "qty": "number"}], "meta": {"page": "number"}}


def test_json_shape_empty_array_stays_empty():
    assert _json_shape({"tags": []}) == {"tags": []}


def test_shape_of_json_text_returns_empty_string_for_non_json():
    assert _shape_of_json_text("not json at all") == ""
    assert _shape_of_json_text("") == ""
    assert _shape_of_json_text(None) == ""


def test_shape_of_json_text_real_secret_value_never_survives():
    """The exact privacy guarantee this feature exists to preserve: a real
    token value is replaced by its type name, never itself, anywhere in
    the output."""
    payload = json.dumps({"share_token": "eq.LCd4nGOLkA1e-KhCK6RdlSkpyxgH2Zos", "user_email": "real@person.com"})
    shape_json = _shape_of_json_text(payload)
    assert "LCd4nGOLkA1e-KhCK6RdlSkpyxgH2Zos" not in shape_json
    assert "real@person.com" not in shape_json
    assert json.loads(shape_json) == {"share_token": "string", "user_email": "string"}


def test_body_shape_and_response_shape_computed_from_post_data_and_response_body():
    events = [
        {
            "event_type": "request", "url": "/api/orders", "method": "POST", "resource_type": "fetch",
            "post_data": json.dumps({"order_id": "abc-123"}),
        },
        {
            "event_type": "response", "url": "/api/orders", "status": 201,
            "body": {"text": json.dumps({"id": "def-456", "created": True})},
        },
    ]
    result = filter_meaningful_requests(events)
    assert len(result) == 1
    assert json.loads(result[0]["body_shape"]) == {"order_id": "string"}
    assert json.loads(result[0]["response_shape"]) == {"id": "string", "created": "boolean"}
    assert "abc-123" not in str(result[0])
    assert "def-456" not in str(result[0])


def test_non_json_response_body_produces_empty_shape_not_an_error():
    events = [
        {"event_type": "request", "url": "/api/ping", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response", "url": "/api/ping", "status": 200, "body": {"text": "<html>not json</html>"}},
    ]
    result = filter_meaningful_requests(events)
    assert result[0]["response_shape"] == ""


def test_capture_error_event_types_never_match_the_keep_filter():
    """request_capture_error/request_failed_capture_error carry no
    resource_type at all - they must never spuriously pass the xhr/fetch
    filter (they're not "request" event_type in the first place)."""
    events = [
        {"event_type": "request_capture_error", "url": "/api/x", "error": "boom"},
        {"event_type": "request_failed_capture_error", "url": "/api/y", "error": "boom"},
    ]
    assert filter_meaningful_requests(events) == []


def test_a_classic_form_post_is_kept_even_though_it_is_a_document():
    """A server-rendered legacy app - this project's whole use case - submits
    data with <form method="post">, which navigates and is resource_type
    "document", not xhr/fetch. Dropping those left the API contract empty."""
    events = [
        {"event_type": "request", "url": "/orders/create", "method": "POST", "resource_type": "document"},
        {"event_type": "response", "url": "/orders/create", "status": 302},
    ]

    result = filter_meaningful_requests(events)

    assert len(result) == 1
    assert result[0]["method"] == "POST"
    assert result[0]["status"] == 302


def test_a_plain_page_navigation_is_still_dropped():
    """The counterpart to the test above: a GET document is someone following
    a link, not an API call, and every crawled page would produce one."""
    events = [
        {"event_type": "request", "url": "/about", "method": "GET", "resource_type": "document"},
        {"event_type": "response", "url": "/about", "status": 200},
    ]

    assert filter_meaningful_requests(events) == []


def test_latency_is_the_gap_between_request_and_response():
    events = [
        {"event_type": "request", "url": "/api/slow", "method": "GET", "resource_type": "fetch",
         "timestamp": 1000.0},
        {"event_type": "response", "url": "/api/slow", "status": 200, "timestamp": 1002.5},
    ]

    assert filter_meaningful_requests(events)[0]["latency_ms"] == 2500


def test_latency_is_none_when_no_response_ever_arrived():
    """A failed request has a send time and nothing else - reporting 0 ms
    would read as "instantaneous" rather than "never answered"."""
    events = [
        {"event_type": "request", "url": "/api/down", "method": "GET", "resource_type": "xhr",
         "timestamp": 1000.0},
        {"event_type": "request_failed", "url": "/api/down", "failure_text": "refused"},
    ]

    assert filter_meaningful_requests(events)[0]["latency_ms"] is None
