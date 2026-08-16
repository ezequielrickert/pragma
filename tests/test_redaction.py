"""Tests for spiders/content/redaction.py - the pipeline feeds an LLM
prompt, so every path a credential/PII value could travel needs its own
assertion, not just the happy-path JSON case."""
import json

from spiders.content.redaction import REDACTED, redact_body, redact_headers


def test_authorization_header_value_dropped_regardless_of_scheme():
    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abc123.def456"}
    assert redact_headers(headers) == {"Authorization": REDACTED}


def test_cookie_and_set_cookie_headers_dropped():
    headers = {"Cookie": "session=abc123; other=xyz", "Set-Cookie": "session=new; HttpOnly"}
    result = redact_headers(headers)
    assert result["Cookie"] == REDACTED
    assert result["Set-Cookie"] == REDACTED


def test_header_name_matching_is_case_insensitive():
    assert redact_headers({"AUTHORIZATION": "Bearer x"}) == {"AUTHORIZATION": REDACTED}
    assert redact_headers({"cookie": "a=b"}) == {"cookie": REDACTED}


def test_non_sensitive_headers_pass_through_unchanged():
    headers = {"Content-Type": "application/json", "X-Request-Id": "req-42"}
    assert redact_headers(headers) == headers


def test_headers_none_or_empty_returns_empty_dict():
    assert redact_headers(None) == {}
    assert redact_headers({}) == {}


def test_json_body_password_field_dropped_by_key_name():
    body = json.dumps({"username": "alice", "password": "hunter2"})
    result = json.loads(redact_body(body))
    assert result["username"] == "alice"
    assert result["password"] == REDACTED


def test_json_body_sensitive_keys_dropped_regardless_of_shape():
    """A nested object or list under a sensitive key is redacted wholesale,
    not partially recursed into - "credentials": {"user": "a", "pass": "b"}
    must not leak "user" just because the outer key matched."""
    body = json.dumps({"credentials": {"user": "alice", "pass": "hunter2"}, "api_key": ["k1", "k2"]})
    result = json.loads(redact_body(body))
    assert result["credentials"] == REDACTED
    assert result["api_key"] == REDACTED


def test_json_body_non_sensitive_fields_survive():
    body = json.dumps({"order_id": "abc-123", "status": "pending", "count": 3})
    assert json.loads(redact_body(body)) == {"order_id": "abc-123", "status": "pending", "count": 3}


def test_json_body_email_redacted_even_under_an_innocuous_key():
    body = json.dumps({"contact": "jane.doe@example.com"})
    result = json.loads(redact_body(body))
    assert result["contact"] == REDACTED


def test_json_body_card_like_digit_sequence_redacted():
    body = json.dumps({"note": "Card 4111 1111 1111 1111 on file"})
    result = json.loads(redact_body(body))
    assert "4111" not in result["note"]
    assert REDACTED in result["note"]


def test_json_body_jwt_like_token_redacted():
    body = json.dumps({"note": "token was eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"})
    result = json.loads(redact_body(body))
    assert "eyJhbGciOiJIUzI1NiJ9" not in result["note"]


def test_json_body_nested_lists_and_dicts_redacted():
    body = json.dumps({
        "items": [
            {"email": "a@b.com", "qty": 2},
            {"email": "c@d.com", "qty": 1},
        ]
    })
    result = json.loads(redact_body(body))
    assert result["items"][0]["email"] == REDACTED
    assert result["items"][1]["email"] == REDACTED
    assert result["items"][0]["qty"] == 2


def test_non_json_body_email_pattern_still_redacted():
    text = "Please contact support at help@example.com for assistance."
    result = redact_body(text)
    assert "help@example.com" not in result
    assert REDACTED in result


def test_non_json_body_with_no_sensitive_pattern_passes_through():
    text = "<html><body>Welcome to the shop</body></html>"
    assert redact_body(text) == text


def test_empty_body_returns_empty_string():
    assert redact_body(None) == ""
    assert redact_body("") == ""


def test_ordinary_looking_id_is_not_falsely_flagged_as_a_card():
    """A short numeric id must survive - only a 13-19 digit run looks like
    a card number."""
    body = json.dumps({"order_id": "12345"})
    assert json.loads(redact_body(body))["order_id"] == "12345"
