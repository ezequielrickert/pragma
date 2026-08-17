"""Read-only page extraction: the JS payloads and the per-frame discovery pass.
Details: docs/dev/spiders/content/page_extraction.md#module
"""
from __future__ import annotations

import os
from typing import Any, Dict

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


async def run_extraction(page) -> Dict[str, Any]:
    """Run every read-only extraction pass against `page`, including iframes.
    Details: docs/dev/spiders/content/page_extraction.md#run_extraction
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
