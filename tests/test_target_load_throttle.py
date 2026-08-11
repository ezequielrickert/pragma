"""Unit tests for TargetLoadThrottle (src/crawlers/target_load_throttle.py) -
the adaptive backoff + circuit breaker extracted out of Crawl4AICrawler once
that file crossed this repo's file-size SPLIT threshold. Tests the class
directly, with no Crawl4AICrawler/browser involved - pure arithmetic and
async sleep scheduling, not a live crawl.

No pytest-asyncio dependency: each async test wraps its coroutine in
asyncio.run() directly, matching tests/test_crawl4ai_crawler.py's convention.
"""
import asyncio
import time
from typing import List

import pytest

from src.crawlers.target_load_throttle import TargetLoadThrottle


def test_backoff_grows_proportionally_to_how_slow_the_navigation_was():
    """A navigation 2x+ slower than this crawl's fastest one so far must grow
    backoff toward that navigation's own elapsed time (scaled by
    _BACKOFF_PROPORTIONAL_FACTOR), not by a fixed step regardless of how bad
    the slowdown was - a fixed 0.5s step proved far too weak against a real
    degrading target (see record_navigation's docstring)."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=60.0)
    throttle.record_navigation(1.0)  # establishes the 1.0s fastest-navigation baseline
    throttle.record_navigation(3.0)  # 3x the baseline - a real slowdown

    assert throttle._backoff_seconds == pytest.approx(1.5)  # 3.0 * _BACKOFF_PROPORTIONAL_FACTOR


def test_backoff_decays_gradually_when_navigations_stay_close_to_the_fastest_seen():
    """Once grown, backoff must shrink back down while navigations stay
    fast - proportionally (halving each fast navigation), not straight to
    zero in one step, so a transient slowdown doesn't get instantly
    forgotten the moment one fast navigation follows it."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=60.0)
    throttle.record_navigation(1.0)
    throttle.record_navigation(3.0)
    assert throttle._backoff_seconds == pytest.approx(1.5)

    throttle.record_navigation(1.1)  # close to baseline again - not a slowdown

    assert throttle._backoff_seconds == pytest.approx(0.75)  # 1.5 * (1 - _BACKOFF_PROPORTIONAL_FACTOR)


def test_backoff_never_exceeds_its_configured_ceiling():
    """Repeated slowdowns must not grow backoff past backoff_ceiling_seconds -
    an unbounded delay would eventually stall the crawl outright."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=1.0, circuit_breaker_cooldown_seconds=60.0)
    throttle.record_navigation(1.0)
    for _ in range(10):
        throttle.record_navigation(5.0)  # every call is a fresh, real slowdown

    assert throttle._backoff_seconds == pytest.approx(1.0)


def test_backoff_disabled_when_ceiling_is_none():
    """backoff_ceiling_seconds=None must skip backoff tracking entirely -
    a target that never needs this shouldn't pay for it."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=None, circuit_breaker_cooldown_seconds=60.0)
    throttle.record_navigation(1.0)
    throttle.record_navigation(100.0)

    assert throttle._backoff_seconds == 0.0


def test_target_slowdown_ratio_reflects_the_most_recent_navigation():
    """target_slowdown_ratio (read by MechanicalCrawler to taper concurrency)
    must track elapsed/fastest for the *latest* navigation, live - not a
    ratchet that only ever grows, and updated even with backoff disabled."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=None, circuit_breaker_cooldown_seconds=60.0)
    throttle.record_navigation(1.0)
    assert throttle.target_slowdown_ratio == pytest.approx(1.0)

    throttle.record_navigation(4.0)
    assert throttle.target_slowdown_ratio == pytest.approx(4.0)

    throttle.record_navigation(1.2)  # a later fast navigation - ratio must drop back down
    assert throttle.target_slowdown_ratio == pytest.approx(1.2)


def test_circuit_breaker_trips_on_a_severe_slowdown():
    """A navigation >= _SEVERE_SLOWDOWN_MULTIPLIER times the fastest seen
    must trip the circuit breaker - wait_before_navigation then blocks for
    the full cooldown, not just the (much smaller) backoff delay."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=30.0)
    throttle.record_navigation(1.0)
    throttle.record_navigation(5.0)  # 5x the baseline - severe, not just a slowdown

    assert throttle._circuit_breaker_until > time.monotonic()


def test_circuit_breaker_does_not_trip_on_a_moderate_slowdown():
    """A slowdown under _SEVERE_SLOWDOWN_MULTIPLIER must grow backoff but
    must NOT trip the circuit breaker - that's reserved for genuinely severe
    degradation, not ordinary page-to-page variance."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=30.0)
    throttle.record_navigation(1.0)
    throttle.record_navigation(3.0)  # 3x - a real slowdown, but under the 4x severe threshold

    assert throttle._circuit_breaker_until == 0.0


def test_throttle_sleeps_for_the_current_backoff_before_a_navigation(monkeypatch):
    """wait_before_navigation must actually wait the accumulated backoff,
    not just track it - the tracking alone doesn't slow anything down."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=30.0)
    throttle._backoff_seconds = 1.5
    slept: List[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(throttle.wait_before_navigation())

    assert slept == [1.5]


def test_throttle_honors_the_circuit_breaker_cooldown_over_the_backoff_delay(monkeypatch):
    """Once tripped, wait_before_navigation must sleep the circuit breaker's
    remaining cooldown, not the (much smaller) backoff seconds - the whole
    point is pausing every worker, not just slowing them down."""
    throttle = TargetLoadThrottle(backoff_ceiling_seconds=5.0, circuit_breaker_cooldown_seconds=30.0)
    throttle._backoff_seconds = 1.5
    throttle._trip_circuit_breaker()
    slept: List[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(throttle.wait_before_navigation())

    assert len(slept) == 1
    assert slept[0] == pytest.approx(30.0, abs=0.5)
