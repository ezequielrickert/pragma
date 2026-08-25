/**
 * Shell — sidebar navigation, file loader, stats summary.
 *
 * Shared across pages. Handles:
 * - Sidebar with Graph/Lists/Documents nav items
 * - Site switcher dropdown dynamically loaded from the API
 * - File loader (drag-and-drop + file input) for export.json fallback
 * - Stats summary (node count, edge count, types present)
 */

import { store } from "../graph-store.js";
import { selectionState } from "../selection-state.js";
import { NODE_TYPES, FAMILY_COLORS, RESERVED_TYPES } from "../color-palette.js";
import { initChatFab } from "./chat-fab.js";

/**
 * Initialize the shell — call once on page load/change.
 * @param {"graph"|"lists"|"documents"} activePage
 * @param {string} activeSite
 */
export function initShell(activePage, activeSite) {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  sidebar.innerHTML = `
    <div class="sidebar-brand" style="cursor: pointer;" onclick="window.location.hash = '#/'">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 2v4m0 12v4M2 12h4m12 0h4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
      </svg>
      <span>Pragma Explorer</span>
    </div>

    <!-- Site Selector Dropdown -->
    <div class="sidebar-selector-wrapper">
      <select id="sidebar-site-selector" class="sidebar-selector">
        <option value="${activeSite}" selected>${activeSite}</option>
      </select>
    </div>

    <nav class="sidebar-nav">
      <a href="#/site/${activeSite}/graph" class="nav-item ${activePage === "graph" ? "active" : ""}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/>
          <line x1="8.5" y1="7.5" x2="10.5" y2="16"/><line x1="15.5" y1="7.5" x2="13.5" y2="16"/>
        </svg>
        Graph
      </a>
      <a href="#/site/${activeSite}/lists" class="nav-item ${activePage === "lists" ? "active" : ""}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
          <circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/>
        </svg>
        Lists
      </a>
      <a href="#/site/${activeSite}/documents" class="nav-item ${activePage === "documents" ? "active" : ""}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        Documents
      </a>
    </nav>

    <div class="sidebar-divider"></div>

    <div class="file-loader" id="file-loader" style="display:none">
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
      <div class="footer-note" style="cursor: pointer; text-decoration: underline;" id="btn-finalizar">Finalizar Sesión</div>
      <div class="footer-note">Ladybug Pipeline</div>
    </div>
  `;

  // Fetch and populate site selector
  fetch("/api/sites")
    .then((res) => res.json())
    .then((sites) => {
      const select = document.getElementById("sidebar-site-selector");
      if (select && sites) {
        select.innerHTML = sites
          .map(
            (site) => `
          <option value="${site}" ${site === activeSite ? "selected" : ""}>${site}</option>
        `
          )
          .join("");
      }
    })
    .catch((err) => console.error("Failed to load sites for sidebar", err));

  // Change site selector event
  document.addEventListener("change", (e) => {
    if (e.target && e.target.id === "sidebar-site-selector") {
      const newSite = e.target.value;
      if (newSite && newSite !== activeSite) {
        window.location.hash = `#/site/${newSite}/${activePage}`;
      }
    }
  });

  // Finalizar button event
  const btnFinalizar = document.getElementById("btn-finalizar");
  if (btnFinalizar) {
    btnFinalizar.addEventListener("click", () => {
      if (confirm("Are you sure you want to end the session?")) {
        fetch("/finalizar", { method: "POST" })
          .then((res) => res.text())
          .then((html) => {
            document.body.innerHTML = html;
            localStorage.removeItem("pragma-active-site");
          })
          .catch((err) => alert("Failed to stop server: " + err));
      }
    });
  }

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

  // Initialize the persistent global Chat FAB
  initChatFab();
}

/** Set up file input and drag-and-drop handlers. */
function setupFileLoader() {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const loadAnother = document.getElementById("load-another");

  if (!dropZone || !fileInput || !loadAnother) return;

  // Click to browse
  dropZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) loadFile(e.target.files[0]);
  });

  // Load another / Refresh
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

/** Parse and load an export.json File. */
function loadFile(file) {
  const dropZone = document.getElementById("drop-zone");
  const dropText = dropZone.querySelector(".drop-text");

  dropText.textContent = "Loading file...";
  
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const doc = JSON.parse(e.target.result);
      if (!doc["@graph"]) throw new Error("Missing @graph array");
      
      store.load(doc, file.name, true);
    } catch (err) {
      alert("Error loading export.json: " + err.message);
      dropText.textContent = "Drop export.json";
    }
  };
  reader.readAsText(file);
}

/** Populate statistics in the sidebar footer. */
function updateStats() {
  const statsEl = document.getElementById("sidebar-stats");
  if (!statsEl) return;

  const counts = store.getTypeCounts();
  const sortedTypes = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);

  const typePills = sortedTypes
    .map((type) => {
      const isReserved = RESERVED_TYPES.has(type);
      if (counts[type] === 0 && isReserved) return "";
      return `
        <div class="stats-pill${isReserved ? " reserved" : ""}">
          <span class="swatch" style="background:${FAMILY_COLORS[type]}"></span>
          <span class="type-name">${type}</span>
          <span class="type-count">${counts[type]}</span>
        </div>
      `;
    })
    .filter(Boolean)
    .join("");

  statsEl.innerHTML = `
    <div class="stats-summary">
      <div class="summary-item">
        <span class="val">${store.nodeCount}</span>
        <span class="lbl">Nodes</span>
      </div>
      <div class="summary-item">
        <span class="val">${store.edgeCount}</span>
        <span class="lbl">Edges</span>
      </div>
    </div>
    <div class="stats-types">${typePills}</div>
  `;
}
