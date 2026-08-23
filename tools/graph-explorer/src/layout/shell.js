/**
 * Shell — sidebar navigation, file loader, stats summary.
 *
 * Shared across both pages. Handles:
 * - Sidebar with Graph/Lists nav items
 * - File loader (drag-and-drop + file input) for export.json
 * - Stats summary (node count, edge count, types present)
 */

import { store } from "../graph-store.js";
import { selectionState } from "../selection-state.js";
import { NODE_TYPES, FAMILY_COLORS, RESERVED_TYPES } from "../color-palette.js";

/**
 * Initialize the shell — call once on page load.
 * @param {"graph"|"lists"} activePage
 */
export function initShell(activePage) {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  sidebar.innerHTML = `
    <div class="sidebar-brand">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 2v4m0 12v4M2 12h4m12 0h4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
      </svg>
      <span>Graph Explorer</span>
    </div>

    <nav class="sidebar-nav">
      <a href="./index.html" class="nav-item ${activePage === "graph" ? "active" : ""}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/>
          <line x1="8.5" y1="7.5" x2="10.5" y2="16"/><line x1="15.5" y1="7.5" x2="13.5" y2="16"/>
        </svg>
        Graph
      </a>
      <a href="./lists.html" class="nav-item ${activePage === "lists" ? "active" : ""}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
          <circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/>
        </svg>
        Lists
      </a>
    </nav>

    <div class="sidebar-divider"></div>

    <div class="file-loader" id="file-loader">
      <div class="drop-zone" id="drop-zone">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 12 15 15"/>
        </svg>
        <span class="drop-text">Drop export.json</span>
        <span class="drop-subtext">or click to browse</span>
        <input type="file" id="file-input" accept=".json" />
      </div>
      <div class="loaded-file" id="loaded-file" style="display:none">
        <div class="loaded-name" id="loaded-name"></div>
        <button class="load-another" id="load-another" title="Load different file">↻</button>
      </div>
    </div>

    <div class="sidebar-stats" id="sidebar-stats"></div>

    <div class="sidebar-footer">
      <div class="footer-note">Internal debugging tool</div>
      <div class="footer-note">Ladybug Pipeline</div>
    </div>
  `;

  setupFileLoader();
  
  if (store.isLoaded) {
    document.getElementById("drop-zone").style.display = "none";
    const loadedEl = document.getElementById("loaded-file");
    loadedEl.style.display = "";
    document.getElementById("loaded-name").textContent = store.filename;
    updateStats();
  }

  document.addEventListener("graph-loaded", () => {
    document.getElementById("drop-zone").style.display = "none";
    const loadedEl = document.getElementById("loaded-file");
    loadedEl.style.display = "";
    document.getElementById("loaded-name").textContent = store.filename;
    updateStats();
  });
}

/** Set up file input and drag-and-drop handlers. */
function setupFileLoader() {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const loadAnother = document.getElementById("load-another");

  // Click to browse
  dropZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) loadFile(e.target.files[0]);
  });

  // Load another
  loadAnother.addEventListener("click", () => {
    document.getElementById("loaded-file").style.display = "none";
    dropZone.style.display = "";
    fileInput.value = "";
    fileInput.click();
  });

  // Drag and drop
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) loadFile(e.dataTransfer.files[0]);
  });
}

/** Read and parse a File, then load it into the store. */
function loadFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const doc = JSON.parse(e.target.result);
      if (!doc["@graph"]) {
        alert("Invalid export.json: missing @graph array");
        return;
      }
      store.load(doc, file.name);

      // Update UI
      document.getElementById("drop-zone").style.display = "none";
      const loadedEl = document.getElementById("loaded-file");
      loadedEl.style.display = "";
      document.getElementById("loaded-name").textContent = file.name;

      // Clear stale selection if the node doesn't exist in the new data
      if (selectionState.selectedNodeId && !store.getNode(selectionState.selectedNodeId)) {
        selectionState.clear();
      }
    } catch (err) {
      alert(`Failed to parse JSON: ${err.message}`);
    }
  };
  reader.readAsText(file);
}

/** Update the stats panel after data is loaded. */
function updateStats() {
  const statsEl = document.getElementById("sidebar-stats");
  if (!statsEl || !store.isLoaded) return;

  const counts = store.getTypeCounts();
  const typePills = NODE_TYPES
    .map((type) => {
      const count = counts[type] || 0;
      const reserved = RESERVED_TYPES.has(type);
      if (count === 0 && reserved) return "";
      const color = FAMILY_COLORS[type] || "#6b7280";
      return `
        <div class="stat-type${count === 0 ? " stat-empty" : ""}">
          <span class="stat-swatch" style="background:${color}"></span>
          <span class="stat-label">${type}</span>
          <span class="stat-count">${count}</span>
        </div>
      `;
    })
    .filter(Boolean)
    .join("");

  statsEl.innerHTML = `
    <div class="stats-header">
      <div class="stat-big">${store.nodeCount} <span>nodes</span></div>
      <div class="stat-big">${store.edgeCount} <span>edges</span></div>
    </div>
    <div class="stats-types">${typePills}</div>
  `;
}
