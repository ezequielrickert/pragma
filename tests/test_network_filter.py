"""Unit tests for filter_meaningful_requests (spiders/content/network_filter.py) -
pure function, hand-built event dicts, no browser/crawl4ai dependency."""
import json

from spiders.content.network_filter import _json_shape, _shape_of_json_text, filter_meaningful_requests


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
    ping = next(r for r in result if r["path"] == "/api/ping")
    assert ping == {
        "method": "GET", "host": "", "path": "/api/ping", "query_params": [],
        "resource_type": "fetch",
        "status": 200, "failed": False, "failure_text": None,
        "body_shape": "", "response_shape": "",
        "request_body_excerpt": "", "request_body_length": 0, "request_body_hash": "",
        "response_body_excerpt": "", "response_body_length": 0, "response_body_hash": "",
        "latency_ms": None,
        "status_text": "", "media_type": "", "auth_scheme": "",
    }
    legacy = next(r for r in result if r["path"] == "/api/legacy")
    assert legacy["status"] == 201
    assert legacy["method"] == "POST"


def test_the_query_string_is_stripped_from_path_and_only_param_names_survive():
    """The redaction policy `InferredRequest.query_params` already stated:
    a live query string can carry an order id or a share token, so only
    the sorted, deduplicated parameter *names* may reach storage."""
    events = [
        {
            "event_type": "request", "method": "GET", "resource_type": "fetch",
            "url": "https://x.supabase.co/rest/v1/orders?select=*&order_id=eq.8d206b72-secret",
        },
    ]

    result = filter_meaningful_requests(events)[0]

    assert result["host"] == "x.supabase.co"
    assert result["path"] == "/rest/v1/orders"
    assert result["query_params"] == ["order_id", "select"]
    assert "8d206b72-secret" not in str(result)


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


def test_response_body_is_captured_but_redacted_where_a_credential_pattern_matches():
    """Storage Phase 6: response bodies are captured now (they weren't
    before - openapi.py and a future AI pass need real payload content,
    not just structural shapes), but redact_body() still strips anything
    that looks like a credential wherever it sits in the text."""
    events = [
        {"event_type": "request", "url": "/api/ping", "method": "GET", "resource_type": "fetch"},
        {
            "event_type": "response", "url": "/api/ping", "status": 200,
            "body": {"text": "contact real@person.com for the invite code"},
        },
    ]
    result = filter_meaningful_requests(events)
    assert "body" not in result[0]
    assert "real@person.com" not in result[0]["response_body_excerpt"]
    assert "[REDACTED]" in result[0]["response_body_excerpt"]
    # Ordinary, non-sensitive body content is exactly what this phase exists
    # to preserve - it must survive redaction untouched.
    assert "invite code" in result[0]["response_body_excerpt"]


def test_response_body_excerpt_capped_and_original_length_preserved():
    """A response body is truncated for storage, but byte_length still
    reports the real size so "this response was huge" isn't lost."""
    from spiders.content.network_filter import _PAYLOAD_EXCERPT_BYTES

    huge_body = "x" * (_PAYLOAD_EXCERPT_BYTES * 3)
    events = [
        {"event_type": "request", "url": "/api/big", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response", "url": "/api/big", "status": 200, "body": {"text": huge_body}},
    ]
    result = filter_meaningful_requests(events)[0]
    assert len(result["response_body_excerpt"]) <= _PAYLOAD_EXCERPT_BYTES
    assert result["response_body_length"] == len(huge_body)
    assert result["response_body_hash"] != ""


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
    # Storage Phase 6: shapes stay structure-only (the compact form for
    # prompts, unchanged above), but the excerpt fields now carry the real
    # content too - "abc-123"/"def-456" are ordinary ids, not credentials,
    # so redact_body() has no reason to touch them.
    assert "abc-123" in result[0]["request_body_excerpt"]
    assert "def-456" in result[0]["response_body_excerpt"]


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


def test_an_authorization_header_yields_its_scheme_and_never_its_credential():
    """The whole point of reading headers at all: `bearer` is a scheme name,
    the token after it is a secret that must never reach the graph."""
    events = [
        {"event_type": "request", "url": "/api/x", "method": "POST", "resource_type": "fetch",
         "headers": {"Authorization": "Bearer eyJhbGciOi.REDACT-ME"}},
        {"event_type": "response", "url": "/api/x", "status": 201, "headers": {}},
    ]

    result = filter_meaningful_requests(events)[0]

    assert result["auth_scheme"] == "bearer"
    assert "REDACT-ME" not in str(result)


def test_an_api_key_header_is_identified_by_its_name():
    events = [
        {"event_type": "request", "url": "/api/x", "method": "GET", "resource_type": "fetch",
         "headers": {"X-API-Key": "secret-value-here"}},
    ]

    result = filter_meaningful_requests(events)[0]

    assert result["auth_scheme"] == "header:x-api-key"
    assert "secret-value-here" not in str(result)


def test_a_cookie_is_reported_as_a_scheme_without_its_contents():
    events = [
        {"event_type": "request", "url": "/api/x", "method": "GET", "resource_type": "fetch",
         "headers": {"Cookie": "session=abc123; user=real@person.com"}},
    ]

    result = filter_meaningful_requests(events)[0]

    assert result["auth_scheme"] == "cookie"
    assert "abc123" not in str(result)
    assert "real@person.com" not in str(result)


def test_a_request_with_no_auth_headers_reports_no_scheme():
    events = [
        {"event_type": "request", "url": "/api/x", "method": "GET", "resource_type": "fetch",
         "headers": {"Accept": "application/json"}},
    ]

    assert filter_meaningful_requests(events)[0]["auth_scheme"] == ""


def test_the_response_media_type_is_read_without_its_charset():
    """The contract assumed application/json for everything; an endpoint
    answering XML or a redirect was described wrongly."""
    events = [
        {"event_type": "request", "url": "/api/x", "method": "GET", "resource_type": "fetch"},
        {"event_type": "response", "url": "/api/x", "status": 200,
         "status_text": "OK", "headers": {"Content-Type": "application/xml; charset=utf-8"}},
    ]

    result = filter_meaningful_requests(events)[0]

    assert result["media_type"] == "application/xml"
    assert result["status_text"] == "OK"
