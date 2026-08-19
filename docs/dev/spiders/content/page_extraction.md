# `spiders/content/page_extraction.py`

## module

The JS payloads `Crawl4AICrawler`'s hooks run against a live page, and the
per-frame discovery pass that drives them. Split out from
`crawl4ai_crawler.py` because this has no dependency on that class's hook
wiring or session bookkeeping: it only needs a Playwright `page` object.

## DISCOVER_COMPONENTS_JS and friends

Loaded once at import time - these are static assets, not per-call state.

## run_extraction

Run every read-only extraction pass against `page`'s main frame, plus
component discovery against every other frame (iframes) - same per-frame
discipline as `PlaywrightScraper._discover_components`, since content
inside an `<iframe>` is invisible to a single `evaluate()` against only
the top-level document.

## pseudo_styles

Main frame only, and deliberately no iframe loop.

This pass reads `document.styleSheets`, and a frame's sheets belong to that
frame's document - the selectors collected here would not match anything inside
one. Running it per frame would cost a round trip per iframe to collect rules
that cannot apply.

Failure degrades to `[]` rather than losing the whole extraction, because the
common cause is not a bug: a site serving its CSS cross-origin makes `cssRules`
throw, and that is indistinguishable from a site declaring no state styles. The
document downstream is the place that says which it might be.
