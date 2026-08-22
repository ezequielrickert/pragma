"""The Graph card (ticket #163, map #159): a real, explorable render of
`export.json`'s Ladybug graph - Cytoscape.js, one color per node `type`
(ADR-0002's vocabulary), pan/zoom, click-to-expand/inspect - replacing
the raw JSON dump `export.json` got from the generic template before.

**The CSS/JS/vocabulary live in `dashboard/graph_assets.py`**, not here -
those are static client-side assets (what the page looks like and how it
behaves in the browser), a different reason to change than this module's
own job: escaping, embedding `export.json`'s content safely, assembling
the page skeleton around those assets.

**CDN-pinned, embedded data, no build step** - the same choice
`dashboard/redoc_renderer.py` already made for Redoc (ticket #124,
ticket #160's own research verdict for this case): Cytoscape.js loads
from jsDelivr pinned to major version 3, and `export.json`'s own content
is embedded inline as a `<script type="application/json">` block rather
than fetched by URL, since a `file://`-opened page can't fetch.

**Pure - no disk access of its own.** `render_graph_page` takes
`export.json`'s already-read content directly, the same "generator
returns content, the pipeline writes it" separation every other renderer
in this package keeps.

Details: docs/dev/dashboard/graph_renderer.md#module
"""
from __future__ import annotations

import json
from html import escape

from .graph_assets import FAMILY_COLORS, RESERVED_TYPES, SCRIPT, SCRIPT_SRC, STYLE


def render_graph_page(export_content: str, site: str) -> str:
    """One self-contained static HTML page rendering `export_content`
    (`export.json`'s raw text, already read by the caller) as an
    explorable Cytoscape.js graph. `graph_assets.SCRIPT`'s two
    `__FAMILY_COLORS__`/`__RESERVED_TYPES__` placeholders are substituted
    with real JSON here, so the palette is computed once, not duplicated
    in the template string itself.
    Details: docs/dev/dashboard/graph_renderer.md#render_graph_page
    """
    script = (
        SCRIPT
        .replace("__FAMILY_COLORS__", json.dumps(FAMILY_COLORS))
        .replace("__RESERVED_TYPES__", json.dumps(list(RESERVED_TYPES)))
    )
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>Graph - {escape(site)}</title>'
        f"<style>{STYLE}</style></head><body>"
        '<div class="topbar">'
        f'<div class="breadcrumb"><a href="index.html">&larr; {escape(site)}</a></div>'
        '<h1>Ladybug Graph</h1>'
        '<input class="search" id="search" placeholder="Search by id or label…">'
        '<div class="legend-row" id="legend"></div>'
        '<div class="view-controls">'
        '<button class="view-btn" onclick="resetToOverview()">Reset to overview</button>'
        '<button class="view-btn" onclick="showAllNodes()">Show all</button>'
        "</div></div>"
        '<div class="body">'
        '<div class="cy-canvas" id="cy"></div>'
        '<div class="hint" id="hint"></div>'
        '<div class="popover" id="popover">'
        '<button id="popover-inspect">View details</button>'
        '<button id="popover-expand">Expand children</button>'
        "</div>"
        '<div class="drawer" id="drawer"><div class="drawer-inner">'
        '<span class="drawer-close" onclick="closeDrawer()">&times;</span>'
        '<div id="detail"></div>'
        "</div></div>"
        "</div>"
        f'<script id="export-data" type="application/json">{export_content}</script>'
        f'<script src="{SCRIPT_SRC}"></script>'
        f"<script>{script}</script>"
        "</body></html>\n"
    )
