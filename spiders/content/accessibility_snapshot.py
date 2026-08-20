"""ARIA snapshot + CDP AXTree capture, docs/adr/0003. Its own module
rather than folded into `page_extraction.py`: extraction there reads
from `page.evaluate(...)` (in-page JS); this reads from Playwright's own
accessibility API and a raw CDP session, a different capture mechanism
entirely, not just a different payload.

**Unverified in this repo's own CI/dev sandbox** - this environment has
no Playwright browser install and no live page to capture against, so
this module is written directly against Playwright's documented
`Locator.aria_snapshot()` and CDP `Accessibility.getFullAXTree` APIs,
not exercised end-to-end here. `tests/test_accessibility_snapshot.py`
covers the parts that don't need a live page: the failure-degrades-to-
empty-strings contract below.

Details: docs/dev/spiders/content/accessibility_snapshot.md#module
"""
from __future__ import annotations

import json
from typing import Any, Tuple


async def capture_accessibility_snapshot(page: Any) -> Tuple[str, str]:
    """`(aria_snapshot_yaml, axtree_json)` for the page's current state, or
    `("", "")` if capture fails - one page whose accessibility tree can't
    be read (a torn-down context, a permission error) must not fail the
    whole discovery pass, the same "degrade this one thing" discipline
    `_discovery_failed`/per-document generator failures already apply.
    Details: docs/dev/spiders/content/accessibility_snapshot.md#capture_accessibility_snapshot
    """
    try:
        aria_snapshot_yaml = await page.locator("body").aria_snapshot()
        cdp = await page.context.new_cdp_session(page)
        try:
            axtree = await cdp.send("Accessibility.getFullAXTree")
        finally:
            await cdp.detach()
        return aria_snapshot_yaml, json.dumps(axtree, ensure_ascii=False)
    except Exception as exc:
        print(f"Warning: accessibility snapshot capture failed for {getattr(page, 'url', '?')!r}: {exc}")
        return "", ""
