"""Regression coverage for `PragmaDeepCrawlStrategy`
(spiders/orchestration/deep_crawl_strategy.py) - issue #239: the route-shape
visit cap, `clean_url`-based dedup, and redirect-resolved identity
`UrlFrontier` used to enforce, now carried by `can_process_url`/
`link_discovery` instead.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from spiders.orchestration.deep_crawl_strategy import PragmaDeepCrawlStrategy


@dataclass
class _FakeCrawlResult:
    """Duck-typed stand-in for `crawl4ai.models.CrawlResult` - only the
    fields `BFSDeepCrawlStrategy.link_discovery` and this module's own
    override actually read."""

    url: str
    links: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    redirected_url: Optional[str] = None
    metadata: Optional[dict] = None


def _links(*hrefs: str) -> Dict[str, List[Dict[str, str]]]:
    return {"internal": [{"href": href} for href in hrefs]}


async def _discover(strategy: PragmaDeepCrawlStrategy, result: _FakeCrawlResult, depth: int = 0):
    visited: set = set()
    next_level: list = []
    depths: Dict[str, int] = {}
    await strategy.link_discovery(result, result.url, depth, visited, next_level, depths)
    return next_level


def test_can_process_url_rejects_out_of_scope_urls():
    strategy = PragmaDeepCrawlStrategy(base_url="http://example.com")
    assert asyncio.run(strategy.can_process_url("http://elsewhere.com/page", 1)) is False


def test_can_process_url_allows_in_scope_urls():
    strategy = PragmaDeepCrawlStrategy(base_url="http://example.com")
    assert asyncio.run(strategy.can_process_url("http://example.com/page", 1)) is True


def test_can_process_url_bypasses_the_scope_gate_for_the_entry_point():
    """depth 0 is the crawl's own start_url - always processed, same as
    UrlFrontier.enqueue(start_url) never being scope-checked against itself."""
    strategy = PragmaDeepCrawlStrategy(base_url="http://example.com")
    assert asyncio.run(strategy.can_process_url("http://example.com/anything", 0)) is True


def test_can_process_url_enforces_the_route_shape_cap():
    strategy = PragmaDeepCrawlStrategy(max_visits_per_route_shape=1)
    strategy._route_shape_visits["example.com/o/{token}"] = 1

    assert asyncio.run(strategy.can_process_url("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN", 1)) is False


def test_can_process_url_allows_more_instances_when_the_cap_is_raised():
    strategy = PragmaDeepCrawlStrategy(max_visits_per_route_shape=2)
    strategy._route_shape_visits["example.com/o/{token}"] = 1

    assert asyncio.run(strategy.can_process_url("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN", 1)) is True


def test_prime_route_shape_visits_carries_a_previous_runs_counts_forward():
    strategy = PragmaDeepCrawlStrategy(max_visits_per_route_shape=1)
    strategy.prime_route_shape_visits(["example.com/o/{token}"])

    assert asyncio.run(strategy.can_process_url("http://example.com/o/aB1cD2eF3gH4iJ5kL6mN", 1)) is False


def test_link_discovery_dedups_a_later_link_by_clean_url_not_literal_string():
    """Two literal hrefs that clean_url() collapses to the same key (here:
    with vs. without a trailing slash) must not both survive into next_level."""
    strategy = PragmaDeepCrawlStrategy()

    first = asyncio.run(_discover(strategy, _FakeCrawlResult(
        url="http://example.com/start", links=_links("http://example.com/page"),
    )))
    assert [url for url, _ in first] == ["http://example.com/page"]

    second = asyncio.run(_discover(strategy, _FakeCrawlResult(
        url="http://example.com/other", links=_links("http://example.com/page/"),
    )))
    assert second == []


def test_link_discovery_never_removes_an_earlier_calls_own_entries():
    """next_level accumulates across every result in a BFS level - a later
    call's own dedup pass must only touch what it itself appended."""
    strategy = PragmaDeepCrawlStrategy()
    visited: set = set()
    next_level: list = []
    depths: Dict[str, int] = {}

    asyncio.run(strategy.link_discovery(
        _FakeCrawlResult(url="http://example.com/a", links=_links("http://example.com/one")),
        "http://example.com/a", 0, visited, next_level, depths,
    ))
    asyncio.run(strategy.link_discovery(
        _FakeCrawlResult(url="http://example.com/b", links=_links("http://example.com/two")),
        "http://example.com/b", 0, visited, next_level, depths,
    ))

    assert {url for url, _ in next_level} == {"http://example.com/one", "http://example.com/two"}


def test_link_discovery_counts_the_redirect_destination_not_the_pre_redirect_link():
    """A link discovered pointing at a bare, redirecting URL must have its
    *resolved* destination's route shape counted - the frontier-level
    counterpart of UrlFrontier.requeue()'s resolved-url fix - so a second,
    independent link to that same resolved destination is capped out."""
    strategy = PragmaDeepCrawlStrategy(max_visits_per_route_shape=1)

    asyncio.run(_discover(strategy, _FakeCrawlResult(
        url="http://example.com/start", links=_links("http://example.com/bare-entry"),
    )))
    # The bare entry point's own fetch resolved to a session-hash URL.
    asyncio.run(_discover(strategy, _FakeCrawlResult(
        url="http://example.com/bare-entry",
        redirected_url="http://example.com/o/aB1cD2eF3gH4iJ5kL6mN",
    )))

    # A second, independent link to the same resolved destination's route
    # shape is now capped out.
    assert asyncio.run(
        strategy.can_process_url("http://example.com/o/zY9xW8vU7tS6rQ5pO4nM", 1)
    ) is False
