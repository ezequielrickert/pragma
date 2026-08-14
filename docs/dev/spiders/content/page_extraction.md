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

## extract_pseudo_styles

Reads the `:hover`/`:focus` styles a stylesheet *declares*, rather than
forcing the pseudo-state through the debugger protocol and re-reading
computed styles.

Two reasons. It needs no CDP session, so it works through the same
`page.evaluate` every other extraction here uses. And a declared value is
what a design token *is*: `#1a4f9c` as an author wrote it beats the same
colour resolved through whatever the element happened to inherit.

**Known limit, and there is no way around it**: a cross-origin stylesheet
throws on `.cssRules`. A site serving its CSS from a CDN therefore reports
fewer state styles than it has, and the design-token document says so
rather than letting the absence read as "this site declares none".

Specificity is not resolved - later rules simply win. Full cascade
resolution is not worth reimplementing for a token inventory, where the
question is which values exist rather than which one applies to a given
element.

## walk_tab_order

Presses Tab for real, instead of walking the focusable elements in DOM
order.

That is the whole point. WCAG 2.4.3 is about a tab order that disagrees
with reading order, and the usual cause is a positive `tabindex` - which
is invisible to any check that reads the document instead of driving it.
Each stop records both where focus went and its DOM position, so the two
can be compared.

Stops early when focus returns somewhere already visited (the sequence has
wrapped), and gives up at `_MAX_TAB_STEPS`. The cap is not cosmetic: a
page with a focus trap would otherwise loop forever, and a focus trap is
exactly the kind of page this is run against.

Runs **last** among the measurement extractions, because it leaves focus
somewhere the crawl put it - anything read afterwards would be observing a
page in a state the measurement itself created.
