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
        # Queue, not deque - workers await new items; .join() detects "done".
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#_queue
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._queued: Set[str] = set()  # clean_url keys already enqueued or visited, dedup guard
        # Narrower than _queued - guards a same-destination-redirect race.
        # Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#in_flight
        self._in_flight: Set[str] = set()
        self._route_shape_visits: Dict[str, int] = {}  # route_shape() key -> completed-visit count

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

    def requeue(self, url: str) -> None:
        """Put `url` straight onto the queue, bypassing `enqueue`'s scope/
        dedup/route-shape gates - for `_worker`'s redirect-requeue case only.
        Details: docs/dev/spiders/orchestration/mechanical_loop/frontier.md#requeue
        """
        self._queue.put_nowait(url)

    async def get(self) -> str:
        return await self._queue.get()

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
