# spiders/orchestration/best_first_strategy.py

## Module

Part of the map at [issue #245](https://github.com/ezequielrickert/pragma/issues/245)
("Adopt crawl4ai's native BestFirstCrawlingStrategy + streaming"). Built to
close [issue #247](https://github.com/ezequielrickert/pragma/issues/247):
`PragmaBestFirstStrategy`, crawl4ai's native `BestFirstCrawlingStrategy`
carrying `PragmaFrontierMixin`'s frontier rules
(`deep_crawl_strategy.py`) and fixing the `session_id` bug
[`SessionAwareDispatcher`](../browser/crawl4ai_crawler/session_aware_dispatcher.md)
targets ([issue #246](https://github.com/ezequielrickert/pragma/issues/246))
for best-first ordering.

Not yet wired into `CrawlEngineCore` - that's a separate ticket on the same
map ([issue #249](https://github.com/ezequielrickert/pragma/issues/249)).

## PragmaBestFirstStrategy

crawl4ai's `BestFirstCrawlingStrategy` (`crawl4ai/deep_crawling/bff_strategy.py`)
doesn't share a base with `BFSDeepCrawlStrategy` below `DeepCrawlStrategy`,
so it can't inherit `PragmaDeepCrawlStrategy`'s frontier rules directly -
`PragmaFrontierMixin` mixed in ahead of it in the MRO carries them instead.

Defaults `url_scorer` to a `RouteShapeNoveltyScorer`
(`route_shape_scorer.py`) reading this instance's own
`_route_shape_visits`, unless the caller supplies its own.

## _arun_best_first

crawl4ai's own `_arun_best_first` calls `crawler.arun_many()` with no
`dispatcher=` argument, so it always falls back to a bare
`MemoryAdaptiveDispatcher` - the one with the dropped-`session_id` bug
issue #246 fixes. `_arun_best_first` is the single place that call happens
(`_arun_batch`/`_arun_stream` both just delegate to it), so this overrides
only that one method, reproducing its body unchanged except for passing
`dispatcher=self._dispatcher` (a `SessionAwareDispatcher` instance built
once per strategy instance, not per batch, so its memory/rate-limiting
state persists across the whole crawl).

Kept as a near-verbatim copy of crawl4ai's own method rather than a
minimal diff-by-composition, because crawl4ai exposes no extension point
here at all (no `dispatcher=` param, no hook called before the
`arun_many()` call) - the same tradeoff `SessionAwareDispatcher`'s own
docstring documents at a smaller scale.
