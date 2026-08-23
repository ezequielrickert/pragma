/**
 * Lists page — tabbed, sortable node table with search and detail drawer.
 *
 * Renders one tab per node type, a search bar to filter the current table,
 * and a sortable HTML table of all nodes matching the active type + query.
 * Clicking a row selects the node and opens the detail drawer; cross-page
 * selection via sessionStorage is handled automatically.
 *
 * DOM contract (expected IDs in lists.html):
 *   #lists-tabs        – container for the type tab bar
 *   #lists-search-bar  – container for search input + result count
 *   #lists-table-area  – scrollable area where the <table> is rendered
 *   .drawer / .drawer-inner – shared detail panel
 */

import { store } from "../graph-store.js";
import { selectionState } from "../selection-state.js";
import { NODE_TYPES, FAMILY_COLORS, RESERVED_TYPES, typeBadgeHtml } from "../color-palette.js";
import { renderNodeDetail, attachDetailClickHandlers } from "../node-detail.js";

/* ── Module-level state ── */

/** Currently active type tab. */
let activeType = NODE_TYPES[0];

/** Current sort column key and direction. */
let sortCol = "label";
let sortAsc = true;

/** Current search query (lower-cased for matching). */
let searchQuery = "";

/* ── Column definitions ── */

/**
 * Each column defines how to read, render, and size a cell.
 * `key` is used for sort state; `get` pulls a comparable value from a node.
 */
const COLUMNS = [
  {
    key: "label",
    header: "Label",
    cssClass: "col-label",
    get: (n) => (n.label || n.id).toLowerCase(),
    render: (n) => escHtml(n.label || n.id),
  },
  {
    key: "type",
    header: "Type",
    cssClass: "col-type",
    get: (n) => n.type,
    render: (n) => typeBadgeHtml(n.type),
  },
  {
    key: "id",
    header: "ID",
    cssClass: "col-id",
    get: (n) => n.id,
    render: (n) => `<span title="${escAttr(n.id)}">${escHtml(truncateId(n.id))}</span>`,
  },
  {
    key: "out",
    header: "Out",
    cssClass: "col-out",
    get: (n) => store.getEdges(n.id).outgoing.length,
    render: (n) => `<span class="td-out">${store.getEdges(n.id).outgoing.length}</span>`,
  },
  {
    key: "in",
    header: "In",
    cssClass: "col-in",
    get: (n) => store.getEdges(n.id).incoming.length,
    render: (n) => `<span class="td-in">${store.getEdges(n.id).incoming.length}</span>`,
  },
];

/* ── Public entry point ── */

/**
 * Initialise the Lists page.
 * Call once after the DOM is ready and the shell has been set up.
 */
export function initListsPage() {
  renderTabs();
  renderSearchBar();
  renderTable();

  // If a node was selected on another page, jump to its tab
  restoreSelection();

  /* ── Event wiring ── */

  // Re-render when new data is loaded
  document.addEventListener("graph-loaded", () => {
    renderTabs();
    renderTable();
    restoreSelection();
  });

  // React to selection changes (e.g. from the detail drawer's edge cards)
  document.addEventListener("selection-changed", (e) => {
    const { nodeId } = e.detail;
    if (!nodeId) {
      closeDrawer();
      clearRowHighlight();
      return;
    }

    const node = store.getNode(nodeId);
    if (!node) return;

    // Switch tabs if the selected node lives under a different type
    if (node.type !== activeType) {
      activateTab(node.type);
    } else {
      highlightAndScroll(nodeId);
    }

    openDrawerForNode(nodeId);
  });
}

/* ── Tab bar ── */

/** Render (or re-render) the type tabs into #lists-tabs. */
function renderTabs() {
  const container = document.getElementById("lists-tabs");
  if (!container) return;

  const counts = store.getTypeCounts();

  container.innerHTML = NODE_TYPES
    .map((type) => {
      const count = counts[type] || 0;
      // Hide reserved types that have no nodes
      if (count === 0 && RESERVED_TYPES.has(type)) return "";

      const color = FAMILY_COLORS[type] || "#6b7280";
      const isActive = type === activeType;

      return `
        <button
          class="type-tab${isActive ? " active" : ""}"
          data-type="${escAttr(type)}"
        >
          <span class="tab-swatch" style="background:${color}"></span>
          ${escHtml(type)}
          <span class="tab-count">${count}</span>
        </button>
      `;
    })
    .filter(Boolean)
    .join("");

  // Attach click handlers
  container.querySelectorAll(".type-tab").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.type));
  });
}

/**
 * Switch to a specific type tab, re-render the table, and reset search.
 * @param {string} type - Node type key (e.g. "Pantalla")
 */
function activateTab(type) {
  if (!NODE_TYPES.includes(type)) return;

  activeType = type;
  searchQuery = "";

  // Reset the search input visually
  const searchInput = document.querySelector(".lists-search");
  if (searchInput) searchInput.value = "";

  // Reset sort to default
  sortCol = "label";
  sortAsc = true;

  renderTabs();   // update active state
  renderTable();

  // Re-highlight the selected node if it belongs to this tab
  if (selectionState.selectedNodeId) {
    highlightAndScroll(selectionState.selectedNodeId);
  }
}

/* ── Search bar ── */

/** Render the search input and result count into #lists-search-bar. */
function renderSearchBar() {
  const container = document.getElementById("lists-search-bar");
  if (!container) return;

  container.innerHTML = `
    <input
      class="lists-search"
      type="text"
      placeholder="Search by label or ID…"
      aria-label="Filter nodes"
    />
    <span class="lists-result-count"></span>
  `;

  const input = container.querySelector(".lists-search");
  input.addEventListener("input", (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    renderTable();
  });
}

/* ── Table rendering ── */

/**
 * Build and inject the full <table> for the active type + search query.
 * Sorting is applied before rendering; the current column gets a visual
 * indicator (▲ / ▼).
 */
function renderTable() {
  const container = document.getElementById("lists-table-container");
  if (!container) return;

  // Gather nodes for the active type, filtered by search
  let nodes = store.getNodesByType(activeType);
  if (searchQuery) {
    nodes = nodes.filter(
      (n) =>
        (n.label || "").toLowerCase().includes(searchQuery) ||
        n.id.toLowerCase().includes(searchQuery)
    );
  }

  // Update result count
  const countEl = document.querySelector(".lists-result-count");
  if (countEl) {
    const total = store.getNodesByType(activeType).length;
    countEl.textContent = searchQuery
      ? `${nodes.length} of ${total}`
      : `${total} nodes`;
  }

  // Sort
  const col = COLUMNS.find((c) => c.key === sortCol) || COLUMNS[0];
  nodes = [...nodes].sort((a, b) => {
    const va = col.get(a);
    const vb = col.get(b);
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });

  // Build header
  const ths = COLUMNS.map((c) => {
    const isSorted = c.key === sortCol;
    const arrow = isSorted ? (sortAsc ? "▲" : "▼") : "▲";
    return `<th class="${c.cssClass}${isSorted ? " sorted" : ""}" data-col="${c.key}">
      ${c.header} <span class="sort-arrow">${arrow}</span>
    </th>`;
  }).join("");

  // Build rows
  const selectedId = selectionState.selectedNodeId;
  const rows = nodes
    .map((n) => {
      const isSelected = n.id === selectedId;
      const cells = COLUMNS.map((c) => `<td class="${c.cssClass}">${c.render(n)}</td>`).join("");
      return `<tr data-node-id="${escAttr(n.id)}"${isSelected ? ' class="selected"' : ''}>${cells}</tr>`;
    })
    .join("");

  container.innerHTML = `
    <table class="node-table">
      <thead><tr>${ths}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  // Wire header sort clicks
  container.querySelectorAll(".node-table th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.col;
      if (sortCol === key) {
        sortAsc = !sortAsc; // toggle direction
      } else {
        sortCol = key;
        sortAsc = true;
      }
      renderTable();
    });
  });

  // Wire row clicks → select node
  container.querySelectorAll(".node-table tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const nodeId = tr.dataset.nodeId;
      selectionState.select(nodeId);
    });
  });
}

/* ── Row highlighting ── */

/** Remove the `selected` class from all rows. */
function clearRowHighlight() {
  document
    .querySelectorAll("#lists-table-area .node-table tbody tr.selected")
    .forEach((tr) => tr.classList.remove("selected"));
}

/**
 * Highlight the row matching `nodeId` and scroll it into view.
 * @param {string} nodeId
 */
function highlightAndScroll(nodeId) {
  clearRowHighlight();

  const row = document.querySelector(
    `#lists-table-area .node-table tbody tr[data-node-id="${CSS.escape(nodeId)}"]`
  );
  if (!row) return;

  row.classList.add("selected");
  row.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/* ── Drawer helpers ── */

/**
 * Open the detail drawer and render the selected node's information.
 * @param {string} nodeId
 */
function openDrawerForNode(nodeId) {
  const drawer = document.querySelector(".drawer");
  const inner = document.querySelector(".drawer-inner");
  if (!drawer || !inner) return;

  renderNodeDetail(nodeId, inner);
  attachDetailClickHandlers(inner);
  drawer.classList.add("open");
}

/** Close the detail drawer. */
function closeDrawer() {
  const drawer = document.querySelector(".drawer");
  if (drawer) drawer.classList.remove("open");
}

/* ── Selection restoration ── */

/**
 * If a node was already selected (e.g. on the Graph page before
 * navigating here), switch to its type tab and highlight it.
 */
function restoreSelection() {
  const nodeId = selectionState.selectedNodeId;
  if (!nodeId) return;

  const node = store.getNode(nodeId);
  if (!node) return;

  // Switch to the correct tab (no-op if already active)
  if (node.type !== activeType) {
    activateTab(node.type);
  }

  highlightAndScroll(nodeId);
  openDrawerForNode(nodeId);
}

/* ── Utility helpers ── */

/**
 * Truncate a node id for table display.
 * Keeps the first 28 characters and appends an ellipsis if longer.
 * @param {string} id
 * @returns {string}
 */
function truncateId(id) {
  return id.length > 28 ? id.slice(0, 27) + "…" : id;
}

/** Escape a string for safe insertion as HTML text content. */
function escHtml(str) {
  const el = document.createElement("span");
  el.textContent = String(str);
  return el.innerHTML;
}

/** Escape a string for safe use inside an HTML attribute value. */
function escAttr(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;");
}
