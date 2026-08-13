# `src/crawlers/page_extraction.py`

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

## run_accessibility_audit

Injects the vendored axe-core bundle and runs it against the settled page.

`add_script_tag` rather than `evaluate`: axe ships as a UMD bundle that
defines `window.axe` as a side effect, which is a script to load, not an
expression to evaluate.

Returns `[]` on any failure rather than raising. An accessibility audit is
not worth failing a whole measurement pass over, and a page reporting
nothing is distinguishable from a page never visited because the
measurement pass records which pages it reached.

The runner (`js/axe_run.js`) does two things worth knowing:

- **Scopes to WCAG A/AA tags.** Unscoped, axe's best-practice rules come
  along too, and the document fills with findings that are not WCAG.
- **Resolves axe's selectors to this project's own paths.** This is what
  makes the findings attach to `:Component` nodes instead of sitting
  beside the graph as a JSON blob. It carries a third copy of `gp()`,
  deliberately: unifying the helper means editing
  `discover_components.js`, which `wiki/browser-automation-pitfalls.md`
  says not to touch, and ~25 lines of duplicated pure function is the
  cheaper risk.
