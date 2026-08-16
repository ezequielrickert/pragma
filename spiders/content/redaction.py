"""Redacts credentials and PII from captured network bodies/headers before
they ever reach storage. This pipeline feeds an LLM prompt - a captured
`Authorization` header or a `password` field left in a request body would
sit in that prompt. Runs at capture time, not read time: once a secret is
written to storage it has already leaked, so there is no "redact on the
way out" that undoes an unredacted write.

Two independent layers, applied together:
1. Key-based (JSON bodies only): a value whose own key name looks
   sensitive (`password`, `token`, `api_key`, ...) is dropped outright,
   regardless of its shape - this is the reliable, low-false-positive path
   since it acts on something the payload's author already named.
2. Pattern-based (every string, JSON or not): email addresses, card-like
   digit sequences, and long token/JWT-looking strings are redacted
   wherever they appear, including inside a value whose key gave no hint.
   Erring toward over-redaction is the correct failure mode here - a false
   positive costs a little information; a false negative leaks a secret.

Details: docs/dev/spiders/content/redaction.md#module
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

REDACTED = "[REDACTED]"

# Headers whose value is dropped outright regardless of content - an
# Authorization/Cookie/Set-Cookie value is a credential by definition, not
# just something that might look like one.
_SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie"}

# JSON object keys whose value gets dropped outright, whatever shape it is -
# a nested object or list under "credentials" is redacted wholesale, not
# partially recursed into.
_SENSITIVE_KEY_PATTERN = re.compile(
    r"password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"session[_-]?id|auth|credential|ssn|cvv|ccv|card[_-]?num",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# 13-19 digits, optionally space/dash-separated every few digits - loose
# enough to catch a formatted card number without a full Luhn check.
_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# A JWT (three dot-separated base64url segments) or a bare long
# token-looking string (32+ alphanumeric/underscore/dash characters).
_TOKEN_PATTERN = re.compile(
    r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b|\b[A-Za-z0-9_-]{32,}\b"
)


def _redact_patterns(text: str) -> str:
    text = _EMAIL_PATTERN.sub(REDACTED, text)
    text = _TOKEN_PATTERN.sub(REDACTED, text)
    text = _CARD_PATTERN.sub(REDACTED, text)
    return text


def _redact_json_value(value: Any) -> Any:
    """Recurse through an already-parsed JSON value, applying both
    redaction layers. Only a dict can carry a sensitive *key*; every
    string, wherever it sits, still gets pattern-scanned.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SENSITIVE_KEY_PATTERN.search(k) else _redact_json_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_json_value(v) for v in value]
    if isinstance(value, str):
        return _redact_patterns(value)
    return value


def redact_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Redacted copy of `headers` - credential-bearing header names dropped
    outright, every other value pattern-scanned as defense in depth (a
    custom header can carry a token too).
    """
    if not headers:
        return {}
    return {
        name: (REDACTED if name.lower() in _SENSITIVE_HEADER_NAMES else _redact_patterns(value))
        for name, value in headers.items()
    }


def redact_body(text: Optional[str]) -> str:
    """Redacted copy of a request/response body.

    Args:
        text: raw body text, or `None`/`""`.

    Returns:
        `""` for an empty body. A JSON body gets both redaction layers via
        `_redact_json_value`, re-serialized. A non-JSON body (HTML, plain
        text) gets pattern-scanning only - there is no key structure to
        act on.
    """
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _redact_patterns(text)
    return json.dumps(_redact_json_value(parsed))
