"""Unit tests for GET mutation heuristic detection (issue #61).
"""
import pytest

from spiders.browser.crawl4ai_crawler.mutation_heuristics import (
    _overridden_verb,
    looks_like_mutating_get,
)


@pytest.mark.parametrize(
    "url,headers,expected",
    [
        # Standard safe GETs
        ("http://example.com/api/items", None, False),
        ("http://example.com/blog/posts/42", None, False),
        ("http://example.com/resettable-item", None, False),
        ("http://example.com/historydelete-log", None, False),
        ("http://example.com/search?q=delete", None, True),  # query value token
        # Destructive verb path segments
        ("http://example.com/posts/42/delete", None, True),
        ("http://example.com/api/deleteAccount", None, True),
        ("http://example.com/user/cancel_subscription", None, True),
        ("http://example.com/items/remove-all", None, True),
        ("http://example.com/auth/logout", None, True),
        ("http://example.com/cart/checkout", None, True),
        # Method overrides in headers
        (
            "http://example.com/api/items/42",
            {"X-HTTP-Method-Override": "DELETE"},
            True,
        ),
        (
            "http://example.com/api/items/42",
            {"x-http-method-override": "PUT"},
            True,
        ),
        (
            "http://example.com/api/items/42",
            {"x-http-method-override": "GET"},
            False,
        ),
        # Method overrides in query string
        ("http://example.com/api/items/42?_method=DELETE", None, True),
        ("http://example.com/api/items/42?_http_method=PATCH", None, True),
        ("http://example.com/api/items/42?_method=GET", None, False),
    ],
)
def test_looks_like_mutating_get(url, headers, expected):
    assert looks_like_mutating_get(url, headers) == expected


def test_overridden_verb_header_priority():
    headers = {"X-HTTP-Method-Override": "DELETE"}
    assert _overridden_verb("http://example.com?_method=PUT", headers) == "DELETE"
