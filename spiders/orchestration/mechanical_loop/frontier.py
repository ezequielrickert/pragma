"""Which URLs are queued, in flight, or already sampled past
max_visits_per_route_shape - MechanicalCrawler's site-level URL frontier,
independent of how many workers are draining it.
Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#module
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Dict, List, Set

from utils.urls import clean_url, is_in_scope, route_shape
from .config import MechanicalCrawlerConfig

if TYPE_CHECKING:
    from ..interaction_tracker import InteractionTracker


class UrlFrontier:
    """Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#urlfrontier"""

    def __init__(self, tracker: "InteractionTracker", config: MechanicalCrawlerConfig) -> None:
        self.tracker = tracker
        self.base_url = config.base_url
        self.allow_subdomains = config.allow_subdomains
        self.max_visits_per_route_shape = config.max_visits_per_route_shape
        self.max_requeue_attempts = config.max_requeue_attempts
        # Queue, not deque - workers await new items; .join() detects "done".
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#_queue
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._queued: Set[str] = set()  # clean_url keys already enqueued or visited, dedup guard
        # clean_url keys currently sitting un-popped in _queue right now - unlike
        # _queued (permanent, never shrinks), this drains on get() and lets
        # requeue() tell "already going to be handled" apart from "needs a new
        # entry". Always a subset of _queued.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#_pending
        self._pending: Set[str] = set()
        # Narrower than _queued - guards a same-destination-redirect race.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#in_flight
        self._in_flight: Set[str] = set()
        self._route_shape_visits: Dict[str, int] = {}  # route_shape() key -> completed-visit count
        # clean_url key -> how many times requeue() has been called for it,
        # regardless of which interrupted pass called it (a redirect
        # destination many different pages land on shares one counter).
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#_requeue_attempts
        self._requeue_attempts: Dict[str, int] = {}

    def enqueue(self, url: str) -> None:
        """Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#enqueue"""
        key = clean_url(url)
        if key in self._queued or self.tracker.is_visited(key):
            return
        # Single scope choke-point for every discovered/navigated-to URL.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#enqueue-scope-gate
        if self.base_url and not is_in_scope(url, self.base_url, self.allow_subdomains):
            return
        shape = route_shape(url)
        visits = self._route_shape_visits.get(shape, 0)
        if visits >= self.max_visits_per_route_shape:
            print(
                f"Route shape {shape!r} already sampled {visits}x, skipping {url} "
                "to avoid unbounded session-token growth."
            )
            return
        self._queued.add(key)
        self._pending.add(key)
        self._queue.put_nowait(url)

    def enqueue_links(self, links: List[Dict[str, str]]) -> None:
        """Queue every http(s) href; idempotent via `enqueue`'s dedup guard.
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#enqueue_links
        """
        for link in links:
            href = link.get("href", "")
            scheme = link.get("scheme", "")
            if scheme and scheme not in ("http", "https"):
                continue  # mailto:/tel:/javascript: etc - nothing to navigate to
            if href:
                self.enqueue(href)

    def enqueue_scouted(self, url: str) -> None:
        """Re-add a page an earlier, separate `scout_only` run's own
        frontier already fully drained through this same frontier's
        `_queued` dedup set - `enqueue()`'s own dedup guard would silently
        refuse it (the whole point of `_queued` is "never queue the same
        key twice"), so `interact_only` needs its own entry point that
        skips only that guard while keeping the scope gate. Deliberately
        does not touch `_requeue_attempts` or `_route_shape_visits` -
        unlike `requeue()`, this isn't a failure retry, and the scouted set
        already respects `max_visits_per_route_shape` from that earlier
        run's own `enqueue()` gate.
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#enqueue_scouted
        """
        key = clean_url(url)
        if self.base_url and not is_in_scope(url, self.base_url, self.allow_subdomains):
            return
        self._pending.add(key)
        self._queue.put_nowait(url)

    def requeue(self, url: str) -> bool:
        """Put `url` straight onto the queue, bypassing `enqueue`'s scope/
        dedup/route-shape gates - for `_worker`'s redirect-requeue case only.

        Short-circuits to True, without touching `_requeue_attempts`, if this
        key is already pending (un-popped in the queue) or in flight (a
        worker is visiting it right now) - some other interrupted pass
        already requeued the same destination, so this call is absorbed as
        "already going to be handled" rather than a second live entry or a
        counted attempt.

        Returns whether it was actually requeued (or absorbed as a
        duplicate). Past `max_requeue_attempts` for this clean_url key,
        returns False instead - the caller is expected to give up on it for
        good rather than call this again. Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#requeue
        """
        key = clean_url(url)
        if key in self._pending or key in self._in_flight:
            return True
        attempts = self._requeue_attempts.get(key, 0) + 1
        self._requeue_attempts[key] = attempts
        if attempts > self.max_requeue_attempts:
            return False
        self._pending.add(key)
        self._queue.put_nowait(url)
        return True

    def is_known(self, url: str) -> bool:
        """Whether `url` already has a place in this crawl - queued (even if
        not yet dequeued), currently in flight, or already visited.

        The eager pre-check `PageVisitor` runs before treating a mid-pass
        click's navigation as an interruption worth pausing the whole page
        for: a link to a destination this same crawl already knows about
        (the common case for a site-wide nav menu, where nearly every page
        links to nearly every other page) doesn't need a fresh, separate
        pass - `return_to_origin` can just hop the browser back and keep
        draining this page's own frontier.

        No `_pending` check needed here: `_pending` is always a subset of
        `_queued`, so a pending key is already covered by the `_queued` check.
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#is_known
        """
        key = clean_url(url)
        return key in self._queued or key in self._in_flight or self.tracker.is_visited(key)

    def queued_count(self) -> int:
        """How many URLs are still waiting - the denominator a progress line
        needs to distinguish "working through a long list" from "stuck".
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#queued_count
        """
        return self._queue.qsize()

    async def get(self) -> str:
        url = await self._queue.get()
        self._pending.discard(clean_url(url))
        return url

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def is_in_flight(self, key: str) -> bool:
        return key in self._in_flight

    def mark_in_flight(self, key: str) -> None:
        self._in_flight.add(key)

    def clear_in_flight(self, key: str) -> None:
        self._in_flight.discard(key)

    def record_route_shape_visit(self, url: str) -> None:
        shape = route_shape(url)
        self._route_shape_visits[shape] = self._route_shape_visits.get(shape, 0) + 1

    def prime_route_shape_visits(self, shapes: List[str]) -> None:
        """Carry a previous run's sampled route shapes into this one.

        Without this the counter starts at zero every run, so
        `max_visits_per_route_shape` was per-run rather than per-site: five
        short runs sampled up to five URLs of a shape where one long run
        sampled one, and the same site crawled two different ways produced
        two different graphs. Making short runs equivalent to a long one is
        the whole point of the resume path, and this is the piece of state
        that was silently breaking it.

        Counts one per already-finished shape. That is exact at the default
        `max_visits_per_route_shape: 1`, and an undercount above it - the
        graph collapses every literal URL of a shape onto one node, so it
        cannot say whether that node was reached once or three times. Raising
        the setting therefore still lets a resumed run sample more than a
        single run would.
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#prime_route_shape_visits
        """
        for shape in shapes:
            self._route_shape_visits.setdefault(shape, 1)
