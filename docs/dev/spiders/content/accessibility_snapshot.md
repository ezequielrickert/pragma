# `spiders/content/accessibility_snapshot.py`

## module

ARIA snapshot + CDP AXTree capture, docs/adr/0003. Its own module rather
than folded into `page_extraction.py`: extraction there reads from
`page.evaluate(...)` (in-page JS); this reads from Playwright's own
accessibility API and a raw CDP session, a different capture mechanism
entirely, not just a different payload.

**Unverified in this repo's own dev sandbox** - no Playwright browser
install and no live page to capture against were available while this
was written, so it's written directly against Playwright's documented
`Locator.aria_snapshot()` and CDP `Accessibility.getFullAXTree` APIs, not
exercised end-to-end. `tests/test_accessibility_snapshot.py` covers the
part that doesn't need a live page: the failure-degrades-to-empty-strings
contract below.

## capture_accessibility_snapshot

Called once per page discovery
(`spiders/browser/crawl4ai_crawler/hooks.py::before_retrieve_html`), not
per interaction - ADR-0003's snapshot policy (one snapshot per screen in
v1). Returns `("", "")` on any failure rather than raising: one page
whose accessibility tree can't be read (a torn-down context, a
permission error) must not fail the whole discovery pass, the same
"degrade this one thing" discipline `_discovery_failed`/per-document
generator failures already apply elsewhere in this codebase.
