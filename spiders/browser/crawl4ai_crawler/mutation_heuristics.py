"""Pure, stateless heuristics for flagging a GET request that likely mutates
server-side state despite the safe verb. Fixed built-in signals only - no
per-site configuration, no network calls, no DOM access.
Details: docs/dev/spiders/browser/crawl4ai_crawler/mutation_heuristics.md
"""
from __future__ import annotations

import re
from typing import Mapping
from urllib.parse import parse_qsl, urlsplit

_MUTATING_VERBS = frozenset({
    "delete",
    "destroy",
    "remove",
    "cancel",
    "unsubscribe",
    "logout",
    "revoke",
    "archive",
    "approve",
    "reject",
    "confirm",
    "purchase",
    "checkout",
    "pay",
    "vote",
    "follow",
    "unfollow",
    "block",
    "unblock",
    "report",
    "reset",
    "clear",
    "toggle",
    "subscribe",
    "accept",
    "decline",
    "ban",
    "restore",
    "publish",
    "unpublish",
})

_METHOD_OVERRIDE_PARAMS = frozenset({"_method", "_http_method"})
_METHOD_OVERRIDE_HEADER = "x-http-method-override"
_SAFE_VERBS = frozenset({"GET", "HEAD", "OPTIONS"})

_SPLIT_PATTERN = re.compile(r"[/?&=._\-,;:+%]+")
_CAMEL_PATTERN = re.compile(r"([a-z0-9])([A-Z])")


def looks_like_mutating_get(url: str, headers: Mapping[str, str] | None = None) -> bool:
    """True when a nominally-safe GET carries a built-in signal of a
    server-side mutation: a method-override to a non-safe verb, or a
    path/query token matching the built-in destructive-verb dictionary.
    """
    overridden = _overridden_verb(url, headers)
    if overridden is not None and overridden not in _SAFE_VERBS:
        return True
    return _has_mutating_token(url)


def _overridden_verb(url: str, headers: Mapping[str, str] | None = None) -> str | None:
    if headers:
        for key, value in headers.items():
            if key.lower() == _METHOD_OVERRIDE_HEADER and value:
                return value.strip().upper()

    parsed = urlsplit(url)
    if parsed.query:
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in _METHOD_OVERRIDE_PARAMS and value:
                return value.strip().upper()

    return None


def _has_mutating_token(url: str) -> bool:
    parsed = urlsplit(url)
    raw_text = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    segments = _SPLIT_PATTERN.split(raw_text)

    for segment in segments:
        if not segment:
            continue
        sub_tokens = _CAMEL_PATTERN.sub(r"\1 \2", segment).split()
        for token in sub_tokens:
            if token.lower() in _MUTATING_VERBS:
                return True

    return False
