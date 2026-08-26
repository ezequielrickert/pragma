"""crawl4ai `DeepCrawlStrategy` mixin/subclass carrying the frontier rules
`UrlFrontier`/`WorkerPacing`/the hand-rolled worker loop in
`mechanical_loop/loop.py` used to enforce, per issue #236's design: the
route-shape visit cap, `clean_url`-based dedup, and treating a redirected
fetch's resolved destination (not the as-requested URL) as the identity a
dedup/cap decision keys off. Concurrency itself is crawl4ai's own
`arun`/`arun_many`/dispatcher; this mixin only decides which URLs get a
turn. `PragmaBestFirstStrategy` (best-first ordering over the same rules)
lives in `spiders/orchestration/best_first_strategy.py`, which reuses
`PragmaFrontierMixin` from here.
Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#module
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.models import CrawlResult

from utils.urls import clean_url, is_in_scope, route_shape


class PragmaFrontierMixin:
    """The frontier rules shared by every pragma deep-crawl strategy,
    factored out so `PragmaDeepCrawlStrategy` (BFS, below) and
    `PragmaBestFirstStrategy` (best-first, `best_first_strategy.py`) don't
    each carry their own copy - crawl4ai's `BFSDeepCrawlStrategy` and
    `BestFirstCrawlingStrategy` don't share a common ancestor below
    `DeepCrawlStrategy`, so this can't be expressed as a single shared base
    class; a mixin placed before the crawl4ai base in each subclass's MRO
    lets `super()` reach that base's own `can_process_url`/`link_discovery`
    unchanged.
    Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#pragmafrontiermixin
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        allow_subdomains: bool = False,
        max_visits_per_route_shape: int = 1,
        **kwargs: Any,
    ) -> None:
        # Pragma's own crawl has no depth ceiling - UrlFrontier never
        # tracked depth at all, only route shape and max_pages. sys.maxsize
        # stands in for "unbounded" since both crawl4ai base classes'
        # __init__ require a real int.
        # Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#max_depth
        kwargs.setdefault("max_depth", sys.maxsize)
        super().__init__(**kwargs)
        self.base_url = base_url
        self.allow_subdomains = allow_subdomains
        self.max_visits_per_route_shape = max_visits_per_route_shape
        # route_shape() key -> completed-visit count - UrlFrontier's own
        # _route_shape_visits, ported unchanged.
        self._route_shape_visits: Dict[str, int] = {}
        # clean_url() key already counted as seen - each crawl4ai base
        # class's own `visited` set is keyed by crawl4ai's
        # normalize_url_for_deep_crawl, a different canonicalization than
        # pragma's own dedup identity (scheme/www/fragment/trailing-slash
        # insensitive); this is the pragma-keyed twin of it, layered on top
        # rather than replacing it.
        # Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#_seen
        self._seen: Set[str] = set()

    async def can_process_url(self, url: str, depth: int) -> bool:
        """Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#can_process_url"""
        # `PragmaFrontierMixin` has no explicit base of its own - it's
        # designed to sit before a crawl4ai deep-crawl strategy in a
        # subclass's MRO (see `PragmaDeepCrawlStrategy` below,
        # `PragmaBestFirstStrategy` in best_first_strategy.py) so `super()`
        # reaches that strategy's real `can_process_url` at runtime; mypy
        # can only see the mixin's own (empty) base, hence this ignore.
        if not await super().can_process_url(url, depth):  # type: ignore[misc]
            return False
        if self.base_url and not is_in_scope(url, self.base_url, self.allow_subdomains):
            return False
        if depth == 0:
            return True  # the entry point is always visited, same as UrlFrontier.enqueue(start_url)
        shape = route_shape(url)
        return self._route_shape_visits.get(shape, 0) < self.max_visits_per_route_shape

    def is_known(self, url: str) -> bool:
        """Whether `url` already has a place in this crawl - the frontier-
        level counterpart of the old `UrlFrontier.is_known`, consulted by
        `PageInteractionStep` before treating a click's static `<a href>`
        destination as worth a real navigation: a link to a page this crawl
        already fetched (or has queued for a later level) needs no second
        pass. `link_discovery`'s own `_seen` set already carries this - a
        URL only lands in it once `_mark_seen_and_counted` has run for it,
        whether as a just-fetched result or a freshly discovered link.
        Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#is_known
        """
        return clean_url(url) in self._seen

    def prime_route_shape_visits(self, shapes: List[str]) -> None:
        """Carry a previous run's sampled route shapes into this one - ported
        unchanged from `UrlFrontier.prime_route_shape_visits`; see its own
        prior docstring for why an undercount above the default cap is
        acceptable.
        Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#prime_route_shape_visits
        """
        for shape in shapes:
            self._route_shape_visits.setdefault(shape, 1)

    def _resolved_url(self, result: CrawlResult) -> str:
        """The URL this fetch actually landed on: `redirected_url` when the
        request was redirected, `result.url` (the as-requested URL)
        otherwise. Every dedup/route-shape decision below keys off this,
        not the as-requested URL, so two different literal requests that
        redirect to the same destination collapse to one - the frontier-
        level counterpart of `UrlFrontier.requeue`'s "requeue the resolved
        URL, not the original request" fix.
        Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#_resolved_url
        """
        resolved: str = result.redirected_url or result.url
        return resolved

    def _mark_seen_and_counted(self, url: str) -> bool:
        """Record `url`'s `clean_url` key as seen and, the first time only,
        count it toward its route shape. Returns whether it was already
        seen - the shared dedup check both the just-fetched result and
        every newly discovered link go through.
        Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#_mark_seen_and_counted
        """
        key = clean_url(url)
        if key in self._seen:
            return True
        self._seen.add(key)
        shape = route_shape(url)
        self._route_shape_visits[shape] = self._route_shape_visits.get(shape, 0) + 1
        return False

    async def link_discovery(
        self,
        result: CrawlResult,
        source_url: str,
        current_depth: int,
        visited: Set[str],
        next_level: List[Tuple[str, Optional[str]]],
        depths: Dict[str, int],
    ) -> None:
        """Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#link_discovery"""
        self._mark_seen_and_counted(self._resolved_url(result))

        # Only the entries this call appends belong to `result` - next_level
        # is shared and accumulated across every result in the current
        # level, so re-deduping the whole list on each call would drop
        # earlier calls' own entries the moment their key got marked seen.
        # Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#link_discovery-dedup
        before = len(next_level)
        # Same mixin-MRO reasoning as `can_process_url` above: this reaches
        # the crawl4ai base's real `link_discovery` at runtime, invisible
        # to mypy from this mixin's own (empty) base.
        await super().link_discovery(  # type: ignore[misc]
            result, source_url, current_depth, visited, next_level, depths
        )
        kept = [(url, parent) for url, parent in next_level[before:] if not self._mark_seen_and_counted(url)]
        next_level[before:] = kept


class PragmaDeepCrawlStrategy(PragmaFrontierMixin, BFSDeepCrawlStrategy):  # type: ignore[misc]
    # crawl4ai ships no py.typed marker (see pyproject.toml's
    # ignore_missing_imports override), so `BFSDeepCrawlStrategy` resolves
    # to `Any` and mypy strict refuses to subclass it without this ignore -
    # there is no untyped base to fix here.
    """Details: docs/dev/spiders/orchestration/deep_crawl_strategy.md#pragmadeepcrawlstrategy"""
