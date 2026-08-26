"""`RouteShapeNoveltyScorer`: a `crawl4ai.deep_crawling.scorers.URLScorer`
for `PragmaBestFirstStrategy`'s `url_scorer` - crawl4ai's own scorers
(`KeywordRelevanceScorer`, `FreshnessScorer`, ...) score content relevance,
which has no counterpart in pragma's domain; best-first ordering here needs
to favor exploration breadth instead.
Details: docs/dev/spiders/orchestration/route_shape_scorer.md#module
"""
from __future__ import annotations

from typing import Dict

from crawl4ai.deep_crawling.scorers import URLScorer

from utils.urls import route_shape


class RouteShapeNoveltyScorer(URLScorer):  # type: ignore[misc]
    # crawl4ai ships no py.typed marker (see pyproject.toml's
    # ignore_missing_imports override), so `URLScorer` resolves to `Any`
    # and mypy strict refuses to subclass it without this ignore - there
    # is no untyped base to fix here.
    """Favors URLs whose route shape is furthest below
    `max_visits_per_route_shape` - the same route-shape-cap bookkeeping
    `PragmaFrontierMixin` already keeps in `_route_shape_visits`, read
    here rather than duplicated, so scoring always reflects the frontier's
    live counts. A shape with zero visits so far scores `1.0` (most
    favored); a shape already at the cap scores `0.0` - `can_process_url`
    excludes it from the queue by then, but the floor keeps the score
    meaningful for anything read before that gate runs.
    Details: docs/dev/spiders/orchestration/route_shape_scorer.md#routeshapenoveltyscorer
    """

    def __init__(
        self,
        route_shape_visits: Dict[str, int],
        max_visits_per_route_shape: int,
        weight: float = 1.0,
    ) -> None:
        super().__init__(weight)
        self._route_shape_visits = route_shape_visits
        self._max_visits_per_route_shape = max_visits_per_route_shape

    def _calculate_score(self, url: str) -> float:
        """Details: docs/dev/spiders/orchestration/route_shape_scorer.md#_calculate_score"""
        if self._max_visits_per_route_shape <= 0:
            return 0.0  # a cap of zero admits no visits at all - nothing is ever novel
        visits = self._route_shape_visits.get(route_shape(url), 0)
        remaining = max(self._max_visits_per_route_shape - visits, 0)
        return remaining / self._max_visits_per_route_shape
