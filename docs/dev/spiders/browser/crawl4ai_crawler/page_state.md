# `spiders/browser/crawl4ai_crawler/page_state.py`

## module

Free functions, not methods - assembling a `PageState` from a crawl4ai
`CrawlResult` plus this project's own stashed extraction dict needs
nothing from `Crawl4AICrawler` itself beyond the two arguments each
function already takes. Pulled out once `discover_pages_many` needed the
exact same construction a third time (`discover_page` and `_interact`
were already duplicating it).

## resolved_url

`result.url` is always the *requested* URL, unchanged regardless of what
actually happened - confirmed empirically: after a `js_only` click that
navigates to a different page, `result.url` still echoed the original URL
while `result.redirected_url` correctly held the real destination.
`redirected_url` is crawl4ai's own field for "the page we actually ended
up on" (it explicitly re-reads `page.url` right before returning
specifically to capture JS-driven navigation - see
`async_crawler_strategy.py`'s own comment on that line).

## build_page_state

Shared `PageState`-assembly logic, factored out of `discover_page`'s and
`_interact`'s own bodies once `discover_pages_many` needed the exact same
construction a third time. `_interact`'s `PageState` used to omit
`accessibility_violations`/`pseudo_styles`/`tab_order` explicitly; folding
it into this shared function just means those three now default to
whatever `data.get(..., [])` returns - empty, since `on_execution_ended`
(the hook `_interact` triggers) never populates them, only
`before_retrieve_html` does. No behavior change, one fewer near-duplicate
block.
