"""Adaptive pacing against a target server that's straining under load.
Details: docs/dev/crawlers/target_load_throttle.md#module
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

# A navigation this many times slower than the fastest one seen this crawl
# counts as the target server straining, not just page-to-page variance.
# Details: docs/dev/crawlers/target_load_throttle.md#_backoff_slowdown_multiplier
_BACKOFF_SLOWDOWN_MULTIPLIER = 2.0

# Backoff grows toward (elapsed_seconds * this factor) on a slowdown, and
# decays by this same fraction of itself on a fast navigation. Proportional,
# not a fixed step - a single 1s navigation should provoke far more caution
# than a single 6s one, not the same fixed nudge either would under a
# fixed-step design (confirmed too weak against a real degrading target -
# see docs/dev/crawlers/target_load_throttle.md#record_navigation-live-evidence).
# Details: docs/dev/crawlers/target_load_throttle.md#_backoff_proportional_factor
_BACKOFF_PROPORTIONAL_FACTOR = 0.5

# A navigation this many times slower than the fastest one seen this crawl
# trips the circuit breaker - pausing every worker, not just slowing them
# down, since by this point the target is straining badly enough that
# continuing to add load is more likely to make it worse than to finish
# faster. Details: docs/dev/crawlers/target_load_throttle.md#_severe_slowdown_multiplier
_SEVERE_SLOWDOWN_MULTIPLIER = 4.0


class TargetLoadThrottle:
    """Tracks one crawl's navigation timing and decides how much to slow
    down - or fully pause - against a target server that's straining.
    `Crawl4AICrawler` owns one instance and consults it before/after every
    navigation; `MechanicalCrawler` reads `target_slowdown_ratio` off the
    crawler to taper its own worker count (see mechanical_loop.py#_effective_concurrency) -
    this class only tracks/reports facts about the target, it has no idea
    workers or concurrency exist.
    Details: docs/dev/crawlers/target_load_throttle.md#targetloadthrottle
    """

    def __init__(
        self,
        backoff_ceiling_seconds: Optional[float],
        circuit_breaker_cooldown_seconds: float,
    ) -> None:
        self.backoff_ceiling_seconds = backoff_ceiling_seconds
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        # Shared across every worker - one target server, one load signal.
        # Details: docs/dev/crawlers/target_load_throttle.md#_backoff_seconds
        self._backoff_seconds = 0.0
        self._fastest_navigation_seconds: Optional[float] = None
        # time.monotonic() deadline (not the event loop's own clock -
        # record_navigation is a plain sync method, callable with no loop
        # running); every worker's own wait_before_navigation call blocks
        # until this passes, once tripped. 0.0 = never tripped.
        # Details: docs/dev/crawlers/target_load_throttle.md#_circuit_breaker_until
        self._circuit_breaker_until = 0.0
        # Public fact about the target; 1.0 = no observed slowdown.
        # Details: docs/dev/crawlers/target_load_throttle.md#target_slowdown_ratio
        self.target_slowdown_ratio = 1.0

    async def wait_before_navigation(self) -> None:
        """Pause for the circuit breaker's remaining cooldown if tripped,
        otherwise sleep off the crawl's current backoff, before issuing a
        navigation. Every worker calls this before its own navigation, so a
        tripped circuit breaker pauses the whole crawl, not just one worker.
        Details: docs/dev/crawlers/target_load_throttle.md#wait_before_navigation
        """
        cooldown_remaining = self._circuit_breaker_until - time.monotonic()
        if cooldown_remaining > 0:
            await asyncio.sleep(cooldown_remaining)
        elif self._backoff_seconds > 0:
            await asyncio.sleep(self._backoff_seconds)

    def record_navigation(self, elapsed_seconds: float) -> None:
        """Track how this navigation compares to the fastest seen this
        crawl, and react proportionally to how bad it was:
        - within `_BACKOFF_SLOWDOWN_MULTIPLIER`x the floor: decay backoff.
        - beyond it: grow backoff toward this navigation's own elapsed time
          (a 10s navigation earns far more caution than a 6s one - a fixed
          step regardless of severity proved too weak against a real
          degrading target, live-verified against austral.edu.ar: FETCH
          times climbed from ~2.6s avg to ~14.3s avg, peaking past 37s,
          across one continuous ~530-request crawl).
        - beyond `_SEVERE_SLOWDOWN_MULTIPLIER`x: also trip the circuit breaker.
        `target_slowdown_ratio` is always updated (even with backoff
        disabled) - see mechanical_loop.py#_effective_concurrency, which
        reads it independently of whether backoff/circuit-breaker are on.
        Details: docs/dev/crawlers/target_load_throttle.md#record_navigation
        """
        if (
            self._fastest_navigation_seconds is None
            or elapsed_seconds < self._fastest_navigation_seconds
        ):
            self._fastest_navigation_seconds = elapsed_seconds
        self.target_slowdown_ratio = elapsed_seconds / self._fastest_navigation_seconds

        if self.backoff_ceiling_seconds is None:
            return
        if self.target_slowdown_ratio >= _SEVERE_SLOWDOWN_MULTIPLIER:
            self._trip_circuit_breaker()
        if self.target_slowdown_ratio > _BACKOFF_SLOWDOWN_MULTIPLIER:
            target_backoff = elapsed_seconds * _BACKOFF_PROPORTIONAL_FACTOR
            self._backoff_seconds = min(
                max(self._backoff_seconds, target_backoff), self.backoff_ceiling_seconds
            )
        else:
            self._backoff_seconds = max(
                0.0, self._backoff_seconds * (1 - _BACKOFF_PROPORTIONAL_FACTOR)
            )

    def _trip_circuit_breaker(self) -> None:
        """Pause every worker's next navigation for `circuit_breaker_cooldown_seconds`.
        Details: docs/dev/crawlers/target_load_throttle.md#_trip_circuit_breaker
        """
        trip_until = time.monotonic() + self.circuit_breaker_cooldown_seconds
        if trip_until <= self._circuit_breaker_until:
            return  # already tripped further out than this would extend it
        self._circuit_breaker_until = trip_until
        print(
            f"Warning: target navigation time is {_SEVERE_SLOWDOWN_MULTIPLIER:.0f}x+ this crawl's "
            f"fastest - pausing every worker for {self.circuit_breaker_cooldown_seconds:.0f}s to let "
            "the target recover instead of adding more load while it's straining."
        )
