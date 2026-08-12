# `src/crawlers/navigation_suppressor.py`

## module

Keeps one live page rendered for the whole of its interaction pass by
aborting the top-level navigations its own components trigger.

Before this existed, a click that navigated (a nav link, a JS
`window.location`) physically moved the session off the page being
worked on. Everything downstream of that was forced: the pass had to stop
immediately (`wiki/crawl4ai-integration-pitfalls.md`'s first entry - a
selector built for a page the session has left fails with "Execution
context was destroyed", and every remaining frontier item fails the same
way), the page had to be re-queued, and resuming it cost a **second full
fetch** of a page that had already been fetched and rendered once. On a
site with a persistent site-wide nav menu - austral.edu.ar is the case
this was built for - that's one extra fetch per navigating component per
page, on top of a fresh DOM that has lost every same-page reveal the
first pass had opened up.

Suppression removes the cause rather than compensating for the effect.
`NavigationSuppressor` is consulted from `Crawl4AICrawler._route_request`
(a Playwright `page.route()` handler): while an interaction is in flight,
a top-level document request is recorded and aborted, so the browser
never leaves the page. The destination surfaces as
`PageState.suppressed_navigations` and is handled by
`PageVisitor._handle_suppressed_navigation` - queued onto the URL
frontier as a page of its own, with a navigation edge recorded, exactly
as it would have been if the click had been followed. What changes is
only *when* that page is fetched: on its own visit, once, instead of
inline, mid-pass, at the cost of the current page.

Net effect: one URL, one fetch, one uninterrupted pass. This is what
makes "a URL, once fetched, is fully scraped before the next one starts"
literally true rather than approximately true.

**What this deliberately does not cover, and why it's acceptable**:

- **A destination only reachable by POST** (a form submit) is recorded as
  an edge but never enqueued - `PageVisitor` only enqueues `GET`
  destinations, since fetching a POST endpoint with a GET is a different
  resource, not the same screen. That screen is genuinely not visited.
  Accepted deliberately: the alternative (letting submits navigate)
  reintroduces the stop-and-refetch cost for every page carrying a form,
  and a POST result page usually isn't reachable from a crawl's frontier
  anyway.
- **`window.open` / `target="_blank"`** doesn't navigate the page at all,
  it opens a second one - nothing for this to intercept. Unchanged from
  the pre-suppression behaviour.
- **Client-side SPA routing** (`history.pushState`) issues no document
  request either. That case was never a physical navigation to begin
  with, and is already handled by `PageVisitor`'s state-transition branch
  (`docs/dev/crawlers/page_visitor.md#visit-state-transition-branch`).

The pre-suppression path is still fully present and tested - set
`suppress_navigation: false` (see `docs/dev/core/config.md#suppress_navigation`)
to get the stop-and-requeue behaviour back for a site where aborting a
navigation upsets the page's own JS.

## _document_resource_type

Playwright's `resource_type` for a document load. Checked in addition to
`is_navigation_request()` rather than instead of it: `is_navigation_request()`
alone is true for some prefetch/preload cases that never actually replace
the current document, and aborting those would break a page for no gain.

## _armed_attribute

The marker attribute stashed on the Playwright `page` object naming the
session currently suppressing. Kept on the page rather than in a dict on
the suppressor because the route handler's only reliable handle on "which
page is this" is the page itself - and because crawl4ai reuses one page
per session across `arun()` calls, so a page-local flag survives exactly
as long as the session it belongs to.

## NavigationSuppressor

Decides which requests to abort and remembers where each aborted one was
headed. Deliberately owns no Playwright objects and performs no I/O -
`Crawl4AICrawler` does the actual `route.abort()`. That split is what
makes every case below testable without a browser
(`tests/test_navigation_suppressor.py`), while the end-to-end behaviour
gets its own real-Chromium coverage in `tests/test_crawl4ai_crawler.py`.

## _by_session

`session_id -> [{"url", "method"}]`, drained by `take()`. Keyed by
session, not by page, because `Crawl4AICrawlerPool` runs several workers'
sessions through one browser process - one worker's aborted navigation
must never surface in another worker's `PageState`.

## arm

Called from `_on_page_context_created` when, and only when, the current
`arun()` is `js_only` - which is exactly the definition of "this call
issues no `goto()` of its own", so any top-level document request during
it came from the page's own code, i.e. from the interaction just issued.

## disarm

Called for every non-`js_only` call, so a real `discover_page()`
navigation (including any redirect it follows) proceeds untouched.
Disarming explicitly, rather than relying on the attribute being unset,
matters because the same page object is reused across calls: a page
armed for one interaction would otherwise stay armed into the next
navigation and abort the crawl's own `goto()`.

## intercept

Records `request` and reports whether the caller must abort it. Returns
`False` - leave the request alone - for a disarmed page, a non-document
resource, a non-navigation request, an iframe navigating itself, and a
request with no frame at all.

## _is_top_level

Whether the request would replace the whole page rather than reload an
iframe inside it. An iframe re-navigating leaves the outer page, and
every selector discovery built against it, perfectly intact - and
discovery runs per-frame (`discover_components.js`), so an iframe's own
content is real, wanted coverage. Suppressing it would cost that for no
benefit.

`request.frame` *raises* (rather than returning `None`) for a
service-worker-issued request, so the check is guarded: no frame means no
page to navigate, so nothing to suppress.

## take

Hands over and forgets everything suppressed for `session_id`. Called by
`Crawl4AICrawler._interact` immediately after `arun()` returns and
**before** any of its own failure raises, so a failed interaction can
never leave its records behind to be misattributed to the next
interaction's `PageState`.
