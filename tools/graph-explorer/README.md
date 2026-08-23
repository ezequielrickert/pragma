# Ladybug Graph Explorer

Internal debugging tool for exploring the raw graph data produced by the
Ladybug pipeline. **Not a user-facing dashboard** — this is for inspecting
`export.json`'s nodes, edges, and structure without opening each document
separately.

## Quick Start

```bash
cd tools/graph-explorer
npm install
npm run dev
```

Then load any `export.json` from a crawl run via the file picker in the
sidebar. Example file:

```
data/output/graph-card-verify2/www.empanad.app_export_20260822T231928Z.json
```

## Pages

### Graph View (`index.html`)
- Full Cytoscape.js graph with all nodes and edges
- Force-directed layout (cose) with the same parameters as the static dashboard
- Node colors by type, legend toggles, search
- Click a node → detail panel slides in from the right

### Lists View (`lists.html`)
- One tab per node type (Pantalla, Componente, Endpoint, etc.)
- Sortable table with label, type, id, edge counts
- Click a row → same detail panel
- Selection syncs with the Graph view (via sessionStorage)

## Architecture

```
src/
├── color-palette.js    # Shared colors & predicates (matches graph_assets.py)
├── graph-store.js      # Data layer — parses & indexes export.json
├── selection-state.js  # Cross-page selection sync (sessionStorage)
├── node-detail.js      # Shared detail panel component
├── graph/
│   └── graph-page.js   # Cytoscape.js canvas + controls
├── lists/
│   └── lists-page.js   # Type tabs + sortable tables
└── layout/
    ├── shell.js         # Sidebar, file loader, stats
    └── styles.css       # Dark theme (matches dashboard palette)
```

### Data flow

```
export.json → GraphStore.load() → nodesById / nodesByType / edgeIndex
                                      ↓
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
              GraphPage          ListsPage           NodeDetail
              (Cytoscape)       (tables)          (shared component)
                    │                 │
                    └────── SelectionState ──────┘
                         (sessionStorage sync)
```

## Next Step: Diff Between Runs

> **Not implemented yet** — documented here as the natural next step.

The `GraphStore` class is intentionally a single-snapshot store. A future
**diff-between-runs** mode would:

1. Load two `export.json` files (e.g. from consecutive crawls).
2. Instantiate two `GraphStore` instances.
3. Compare them via a new `DiffStore` class that computes:
   - Nodes added / removed / changed (type, label, or edge set).
   - Edges added / removed.
   - Confidence shifts (once `export.json` includes confidence data).
4. Both the Graph view and Lists view would consume `DiffStore` to
   show diff badges (green = added, red = removed, yellow = changed)
   without any rewrite of their core rendering logic.

The current code is structured so this extension requires:
- A new `diff-store.js` module.
- A `DiffBadge` component.
- Minor additions to `graph-page.js` and `lists-page.js` to check for
  diff status when rendering nodes.

No existing module needs to be rewritten.
