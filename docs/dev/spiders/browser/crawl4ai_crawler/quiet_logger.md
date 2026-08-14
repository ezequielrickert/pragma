# `spiders/browser/crawl4ai_crawler/quiet_logger.py`

## module

crawl4ai's own bundled `AsyncLogger` has no per-tag filtering - only a
global `verbose` on/off switch and a minimum `log_level`, neither of which
can silence one specific noisy tag without also silencing everything else
at that level. This module exists to drop exactly one of them:
`tag="CAPTURE"`, which crawl4ai's own response-capture hook logs whenever
`response.text()` raises for a response it can't read as text (routine for
a fire-and-forget analytics beacon like `google.com/ccm/collect` - the
response simply has no readable body to await).

Confirmed by reading crawl4ai 0.9.2's own
`async_crawler_strategy.py::handle_response_capture`: the function's inner
`try/except` around `text_body = await response.text()` has its fallback
assignment commented out (`# text_body = None`), so on that exception path
`text_body` is referenced later in the same function while unbound -
`UnboundLocalError: cannot access local variable 'text_body' where it is
not associated with a value`. That error is itself caught by the *outer*
`try/except` in the same function and logged as a `warning(..., tag="CAPTURE")`
- already handled, appending a `response_capture_error` record in place of
a real one, and never surfacing to anything this project reads back via
`network_filter.py::filter_meaningful_requests`. A real crawl4ai bug, not
anything this project's own hooks or `capture_network_requests=True`
setting causes - not something to fix by disabling network capture
outright, since `filter_meaningful_requests` does read the requests that
*do* capture successfully.

## _CAPTURE_TAG

The one tag this logger drops. Deliberately not a broader "drop all
WARNING-level crawl4ai logs" - other warnings crawl4ai emits (e.g. a real
page load failure) are worth seeing; only this specific, already-caught,
already-non-actionable one is noise.

## QuietCaptureLogger

Subclasses crawl4ai's own `AsyncLogger` rather than reimplementing
`AsyncLoggerBase` from scratch, so every other log level/method
(`info`/`debug`/`success`/`error`/`url_status`/`error_status`/console and
file output/coloring) behaves exactly as crawl4ai's default logger would.
Overrides only `warning()` - the one method that can receive
`tag="CAPTURE"` - and delegates to `super().warning(...)` unchanged for
every other tag.

Constructed in `Crawl4AICrawler.__aenter__` with
`verbose=browser_config.verbose`, matching the `verbose` value
`AsyncWebCrawler` would otherwise have passed to its own default
`AsyncLogger` construction (`self.browser_config.verbose`) - passing a
custom `logger=` is opt-out of that default, not opt-out of matching its
behavior.
