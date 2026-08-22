# `dashboard/graph_renderer.py`

## module

The Graph card (ticket #163, map #159) - a real, explorable render of
`export.json`'s Ladybug graph via Cytoscape.js, replacing the raw JSON
dump `export.json` got from the generic template before. Design settled
by prototype (`docs/prototype-graph-card/`, throwaway `prototype/graph-card`
branch, ticket #162), not by this ticket - five structurally different
layouts were built and reacted to against real crawl data; the winner
("Variant E") is what `dashboard/graph_assets.py`'s `SCRIPT` ships.

**Why the CSS/JS live in a separate module.** `dashboard/graph_assets.py`
holds the static client-side assets (what the page looks like, how it
behaves in the browser) - a different reason to change than this
module's own job, which is escaping and assembling `export.json`'s
content into the page skeleton safely. Same CDN-pinned, embed-data-inline
choice `dashboard/redoc_renderer.py` already made for Redoc.

## render_graph_page

Pure - `export_content` is the caller's already-read text of
`export.json`, embedded inline as a `<script type="application/json">`
block rather than fetched by URL (a `file://`-opened page can't fetch).
Substitutes `graph_assets.SCRIPT`'s `__FAMILY_COLORS__`/`__RESERVED_TYPES__`
placeholders with real JSON, computed once here rather than duplicated in
the template string itself.
