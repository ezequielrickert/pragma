/**
 * GraphPage — Cytoscape.js canvas with legend, search, and detail drawer.
 *
 * Renders all nodes and edges from the GraphStore, colored by type.
 * Reuses the same force-directed layout parameters proven in the
 * static dashboard's graph card (graph_assets.py).
 */

import cytoscape from "cytoscape";
import { store } from "../graph-store.js";
import { selectionState } from "../selection-state.js";
import { renderNodeDetail, attachDetailClickHandlers } from "../node-detail.js";
import {
  FAMILY_COLORS,
  NODE_TYPES,
  RESERVED_TYPES,
  PREDICATES,
} from "../color-palette.js";

/** Cytoscape instance — module-level for cleanup. */
let cy = null;

/** Cose layout params — matches dashboard/graph_assets.py L186. */
const COSE_LAYOUT = {
  name: "cose",
  padding: 40,
  nodeRepulsion: 400000,
  idealEdgeLength: 90,
  nodeOverlap: 20,
  animate: false,
};

const LABEL_MAX = 24;
function truncLabel(label) {
  return label.length > LABEL_MAX ? label.slice(0, LABEL_MAX - 1) + "…" : label;
}

/**
 * Convert the GraphStore's data into Cytoscape elements.
 */
function buildElements() {
  const elements = [];

  for (const node of store.nodesById.values()) {
    elements.push({
      data: {
        id: node.id,
        type: node.type,
        label: node.label || node.id,
      },
    });
  }

  let edgeIdx = 0;
  for (const edge of store.edges) {
    elements.push({
      data: {
        id: `e${edgeIdx++}`,
        source: edge.source,
        target: edge.target,
        predicate: edge.predicate,
      },
    });
  }

  return elements;
}

/** Cytoscape visual style. */
const CY_STYLE = [
  {
    selector: "node",
    style: {
      "background-color": (ele) => FAMILY_COLORS[ele.data("type")] || "#6b7280",
      label: (ele) => truncLabel(ele.data("label")),
      "font-size": 9,
      color: "#e4e7ee",
      "text-outline-width": 2,
      "text-outline-color": "#0f1115",
      width: 22,
      height: 22,
      "text-valign": "bottom",
      "text-margin-y": 4,
      "min-zoomed-font-size": 7,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.4,
      "line-color": "#3a3f4d",
      "target-arrow-color": "#3a3f4d",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
      "curve-style": "bezier",
      opacity: 0.55,
    },
  },
  {
    selector: ".faded",
    style: { opacity: 0.06 },
  },
  {
    selector: ".hidden-family",
    style: { display: "none" },
  },
  {
    selector: ".selected-node",
    style: {
      "border-width": 3,
      "border-color": "#ffffff",
      width: 30,
      height: 30,
    },
  },
];

/**
 * Initialize the graph page — call once after DOM is ready.
 */
export function initGraphPage() {
  const container = document.getElementById("graph-content");
  if (!container) return;

  // Show empty state initially
  renderEmptyState(container);

  // When data loads, build the graph
  document.addEventListener("graph-loaded", () => {
    renderGraphUI(container);
  });

  // If data is already loaded (from sessionStorage scenario), build immediately
  if (store.isLoaded) {
    renderGraphUI(container);
  }
}

/** Render the empty state when no data is loaded. */
function renderEmptyState(container) {
  container.innerHTML = `
    <div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/>
        <line x1="8.5" y1="7.5" x2="10.5" y2="16"/><line x1="15.5" y1="7.5" x2="13.5" y2="16"/>
      </svg>
      <p>Load an <strong>export.json</strong> from the sidebar to explore the graph.</p>
    </div>
  `;
}

/** Build the full graph UI: topbar + canvas + drawer. */
function renderGraphUI(container) {
  if (cy) {
    cy.destroy();
    cy = null;
  }

  const counts = store.getTypeCounts();

  container.innerHTML = `
    <div class="graph-topbar">
      <input type="text" class="graph-search" id="graph-search" placeholder="Search nodes…" />
      <div class="legend-row" id="graph-legend">
        ${NODE_TYPES.map((type) => {
          const count = counts[type] || 0;
          const reserved = RESERVED_TYPES.has(type);
          if (count === 0 && reserved) return "";
          return `
            <span class="family-pill${reserved ? " reserved" : ""}" data-type="${type}">
              <span class="swatch" style="background:${FAMILY_COLORS[type]}"></span>
              ${type}<span class="pill-count">${count === 0 ? "—" : count}</span>
            </span>`;
        }).filter(Boolean).join("")}
      </div>
      <div class="graph-controls">
        <button class="graph-btn" id="btn-fit">Fit</button>
        <button class="graph-btn" id="btn-relayout">Re-layout</button>
      </div>
    </div>
    <div class="graph-container">
      <div class="cy-canvas" id="cy"></div>
      <div class="drawer" id="graph-drawer">
        <div class="drawer-inner" id="graph-detail"></div>
      </div>
    </div>
    <div class="graph-hint" id="graph-hint"></div>
  `;

  // Initialize Cytoscape
  cy = cytoscape({
    container: document.getElementById("cy"),
    elements: buildElements(),
    style: CY_STYLE,
    layout: { ...COSE_LAYOUT },
    minZoom: 0.1,
    maxZoom: 5,
  });

  // Hint text
  updateHint();

  // Node click → open detail
  cy.on("tap", "node", (evt) => {
    const nodeId = evt.target.id();
    selectionState.select(nodeId);
  });

  // Canvas click → close drawer
  cy.on("tap", (evt) => {
    if (evt.target === cy) {
      closeDrawer();
    }
  });

  // Search
  const searchInput = document.getElementById("graph-search");
  searchInput.addEventListener("input", () => {
    applySearch(searchInput.value);
  });

  // Legend pills — toggle visibility
  document.querySelectorAll("#graph-legend .family-pill:not(.reserved)").forEach((pill) => {
    pill.addEventListener("click", () => {
      const type = pill.dataset.type;
      pill.classList.toggle("off");
      cy.nodes(`[type = "${type}"]`).toggleClass("hidden-family");
      recomputeEdgeVisibility();
    });
  });

  // Buttons
  document.getElementById("btn-fit").addEventListener("click", () => {
    cy.animate({ fit: { padding: 40 } }, { duration: 300 });
  });
  document.getElementById("btn-relayout").addEventListener("click", () => {
    cy.layout({ ...COSE_LAYOUT, animate: true, animationDuration: 400 }).run();
  });

  // Listen for selection changes
  document.addEventListener("selection-changed", (e) => {
    const { nodeId } = e.detail;
    highlightNode(nodeId);
    if (nodeId) openDetail(nodeId);
  });

  // If there's an existing selection, show it
  if (selectionState.selectedNodeId && store.getNode(selectionState.selectedNodeId)) {
    highlightNode(selectionState.selectedNodeId);
    openDetail(selectionState.selectedNodeId);
  }
}

/** Highlight a node on the canvas. */
function highlightNode(nodeId) {
  if (!cy) return;
  cy.nodes().removeClass("selected-node");
  if (nodeId) {
    const node = cy.getElementById(nodeId);
    if (node.length) {
      node.addClass("selected-node");
    }
  }
}

/** Search filter — fade non-matching nodes. */
function applySearch(query) {
  if (!cy) return;
  const q = query.trim().toLowerCase();
  if (!q) {
    cy.nodes().removeClass("faded");
    return;
  }
  const matches = cy.nodes().filter(
    (n) => n.id().toLowerCase().includes(q) || n.data("label").toLowerCase().includes(q)
  );
  cy.nodes().addClass("faded");
  matches.removeClass("faded");
  if (matches.length) {
    cy.animate({ fit: { eles: matches, padding: 80 } }, { duration: 300 });
  }
}

/** Recompute edge visibility after family toggle. */
function recomputeEdgeVisibility() {
  if (!cy) return;
  cy.edges().forEach((e) => {
    const hidden = e.source().hasClass("hidden-family") || e.target().hasClass("hidden-family");
    e.toggleClass("hidden-family", hidden);
  });
}

/** Open the detail drawer for a node. */
function openDetail(nodeId) {
  const drawer = document.getElementById("graph-drawer");
  const detailEl = document.getElementById("graph-detail");
  if (!drawer || !detailEl) return;

  drawer.classList.add("open");
  renderNodeDetail(nodeId, detailEl);
  attachDetailClickHandlers(detailEl);
}

/** Close the detail drawer. */
function closeDrawer() {
  const drawer = document.getElementById("graph-drawer");
  if (drawer) drawer.classList.remove("open");
}

/** Update the hint text at the bottom. */
function updateHint() {
  const hintEl = document.getElementById("graph-hint");
  if (!hintEl) return;
  hintEl.textContent = `${store.nodeCount} nodes · ${store.edgeCount} edges — click a node to inspect it`;
}
