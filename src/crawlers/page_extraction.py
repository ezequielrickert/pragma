"""Read-only page extraction: the JS payloads and the per-frame discovery pass.
Details: docs/dev/crawlers/page_extraction.md#module
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

_JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js")


def _load_js(name: str) -> str:
    with open(os.path.join(_JS_DIR, name), encoding="utf-8") as f:
        return f.read()


# Loaded once at import time - these are static assets, not per-call state.
DISCOVER_COMPONENTS_JS = _load_js("discover_components.js")
EXTRACT_LINKS_JS = _load_js("extract_links.js")
EXTRACT_DESCRIPTION_JS = _load_js("extract_description.js")
EXTRACT_METADATA_JS = _load_js("extract_metadata.js")
EXTRACT_TEXT_CONTENT_JS = _load_js("extract_text_content.js")

# Vendored third-party engine, unmodified: axe-core 4.10.2, Deque Systems,
# MPL-2.0. Read once at import like every other asset here, but injected
# with add_script_tag rather than evaluated - it is a UMD bundle that
# defines window.axe, not an expression to evaluate.
# Details: docs/dev/crawlers/page_extraction.md#run_accessibility_audit
AXE_SOURCE = _load_js("axe.min.js")
AXE_RUN_JS = _load_js("axe_run.js")


async def run_accessibility_audit(page) -> List[Dict[str, Any]]:
    """Inject axe-core and return this page's WCAG A/AA violations.

    Args:
        page: a live Playwright page, already settled.

    Returns:
        One dict per violated rule - `rule_id`, `impact`, `criteria`, the
        offending `nodes` (each resolved to this project's own CSS path
        where possible), and `total_nodes` before the per-rule cap. `[]`
        when the page has no violations, and also when axe could not run
        at all: an accessibility audit is not worth failing a whole
        measurement pass over, and a page that reports nothing is
        distinguishable from an absent page by the coverage document.
    Details: docs/dev/crawlers/page_extraction.md#run_accessibility_audit
    """
    try:
        await page.add_script_tag(content=AXE_SOURCE)
        return list(await page.evaluate(AXE_RUN_JS))
    except Exception as exc:
        print(f"Warning: accessibility audit failed on {getattr(page, 'url', '?')!r}: {exc}")
        return []


async def run_extraction(page) -> Dict[str, Any]:
    """Run every read-only extraction pass against `page`, including iframes.
    Details: docs/dev/crawlers/page_extraction.md#run_extraction
    """
    components = await page.evaluate(DISCOVER_COMPONENTS_JS)
    main_url = page.main_frame.url
    for frame in page.frames:
        if frame.url == main_url:
            continue
        try:
            frame_components = await frame.evaluate(DISCOVER_COMPONENTS_JS)
        except Exception as exc:
            print(f"Warning: component discovery failed in frame {frame.url!r}: {exc}")
            continue
        for comp in frame_components:
            comp["frame_url"] = frame.url
        components.extend(frame_components)

    links = list(await page.evaluate(EXTRACT_LINKS_JS))
    for frame in page.frames:
        if frame.url == main_url:
            continue
        try:
            links.extend(await frame.evaluate(EXTRACT_LINKS_JS))
        except Exception as exc:
            print(f"Warning: link extraction failed in frame {frame.url!r}: {exc}")

    description = (await page.evaluate(EXTRACT_DESCRIPTION_JS) or "")[:300]
    metadata = await page.evaluate(EXTRACT_METADATA_JS)
    title = await page.evaluate("() => document.title")

    text_content = list(await page.evaluate(EXTRACT_TEXT_CONTENT_JS))
    for frame in page.frames:
        if frame.url == main_url:
            continue
        try:
            text_content.extend(await frame.evaluate(EXTRACT_TEXT_CONTENT_JS))
        except Exception as exc:
            print(f"Warning: text content extraction failed in frame {frame.url!r}: {exc}")

    return {
        "components": components,
        "links": links,
        "description": description,
        "metadata": metadata,
        "title": title,
        "text_content": text_content,
    }
