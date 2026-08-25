# spiders/orchestration/route_shape_scorer.py

## Module

Part of the map at [issue #245](https://github.com/ezequielrickert/pragma/issues/245).
Built to close [issue #247](https://github.com/ezequielrickert/pragma/issues/247):
the `url_scorer` `PragmaBestFirstStrategy` (`best_first_strategy.py`) orders
its priority queue by. crawl4ai's own scorers (`KeywordRelevanceScorer`,
`FreshnessScorer`, ...) score content relevance against a query or a
domain-tuned heuristic - neither maps onto pragma's exhaustive
route/component coverage goal, so this is net-new rather than a
configuration of an existing crawl4ai scorer.

## RouteShapeNoveltyScorer

Favors URLs whose route shape is furthest below `max_visits_per_route_shape`
- pushes the frontier toward breadth (new route shapes) over depth (more
instances of an already-well-sampled shape), which is what best-first
ordering should optimize for given pragma's coverage goal.

Reads `route_shape_visits` by reference rather than owning a copy - the
same dict `PragmaFrontierMixin.can_process_url` already updates via
`_mark_seen_and_counted`, so a score computed mid-crawl reflects the
frontier's live counts instead of a stale snapshot taken at construction.

A shape with zero visits so far scores `1.0` (most favored); a shape
already at the cap scores `0.0` - `can_process_url` excludes it from the
queue by then, but the floor keeps `_calculate_score` well-defined for
anything scored before that gate runs. A `max_visits_per_route_shape` of
`0` (no visits admitted at all) short-circuits to `0.0` rather than
dividing by zero.
