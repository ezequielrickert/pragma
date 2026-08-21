"""Redoc integration for `openapi.yaml` - the one document Phase B's own
reuse audit found clears ADR-0016 point 2's bar (`dashboard/renderer_audit.py`),
ticket #124.

**CDN-pinned, not vendored.** The ticket names both as acceptable
("Vendor `redoc.standalone.js` (or CDN-pin it)"); vendoring a
multi-hundred-KB third-party bundle into a Python-only backend repo adds
real weight and a re-vendor step on every Redoc release, for a benefit
(offline viewing of this one page) neither audience this dashboard
serves actually needs - Claude Code reads `openapi.yaml` itself
directly, never through Redoc's rendering, and a human reviewer with no
network access still has the same raw file to read. Pinned to Redoc's
major version 2 (`redoc@2` on jsDelivr, a real, documented pinning
strategy the CDN itself supports) rather than a specific patch version -
stating a precise patch number here without a way to verify it's still
current would be exactly the fabricated-specificity this pipeline's own
"never invent" discipline exists to avoid; the major-version pin still
protects against a breaking v3 release while resolving to whatever
patch jsDelivr currently serves.

**Spec embedded inline, not fetched by URL.** Redoc's `spec-url` option
needs a real HTTP(S) fetch, which a browser's `file://` security model
often blocks for a page opened directly rather than served - the same
reason `ADR-0016`'s own static-HTML choice had to rule out anything
requiring a live process. The spec is parsed from YAML to a Python
dict (`yaml`, already a project dependency - `generators/openapi.py`
uses it for the same document) and re-embedded as a `<script
type="application/json">` block Redoc's own `init()` reads directly, so
opening the file works identically double-clicked or served.

Details: docs/dev/dashboard/redoc_renderer.md#module
"""
from __future__ import annotations

import json
from html import escape

import yaml

from core.documents import ProducedDocument
from .document_context import render_context_section

_REDOC_SCRIPT = "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"

_STYLE = """
:root { --bg: #0f1115; --panel: #161922; --border: #2a2f3a; --text: #e4e7ee; --text-dim: #8b93a7; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
.header { padding: 16px 32px; border-bottom: 1px solid var(--border); background: var(--panel); }
.header .breadcrumb { color: var(--text-dim); font-size: 13px; margin-bottom: 8px; }
.header .breadcrumb a { color: var(--text-dim); }
.header h1 { margin: 0 0 2px; font-size: 18px; }
.header .purpose { margin: 0; color: var(--text-dim); font-size: 13px; }
.context { margin: 12px 0 0; padding: 12px; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; }
.context h2 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; color: var(--text-dim); }
.context .example { margin: 8px 0 0; padding: 10px; background: var(--bg); border-radius: 6px; font-size: 12px; overflow-x: auto; }
"""


def render_redoc_page(document: ProducedDocument, content: str) -> str:
    """One self-contained static HTML page for `document`, rendered
    through Redoc - `content` is `openapi.yaml`'s raw YAML text, already
    read by the caller, parsed here into the JSON object Redoc's own
    `init()` API takes. The breadcrumb back to the document's own
    concern page uses `document.name`/`.title` directly, the same pair
    `dashboard/shell.py` groups documents by concern with.
    Details: docs/dev/dashboard/redoc_renderer.md#render_redoc_page
    """
    spec_json = json.dumps(yaml.safe_load(content))
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(document.title)}</title>'
        f"<style>{_STYLE}</style></head><body>"
        f'<div class="header"><div class="breadcrumb">'
        f'<a href="../concern/{escape(document.name)}.html">&larr; {escape(document.title)}</a></div>'
        f'<h1>{escape(document.title)}</h1>'
        f'<p class="purpose">{escape(document.purpose)}</p>'
        f"{render_context_section(document)}</div>"
        f'<div id="redoc-container"></div>'
        f'<script id="spec-data" type="application/json">{spec_json}</script>'
        f'<script src="{_REDOC_SCRIPT}"></script>'
        "<script>Redoc.init(JSON.parse(document.getElementById('spec-data').textContent), {}, "
        "document.getElementById('redoc-container'));</script>"
        "</body></html>\n"
    )
