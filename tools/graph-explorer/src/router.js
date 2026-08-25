/**
 * SPA Router — Client-side Hash Router for Pragma Explorer.
 */

import { store } from "./graph-store.js";
import { initShell } from "./layout/shell.js";
import { initGraphPage } from "./graph/graph-page.js";
import { initListsPage } from "./lists/lists-page.js";
import { loadDocumentsList, loadDocumentEditor } from "./documents/documents-page.js";

/**
 * Initialize the router.
 */
export function initRouter() {
  window.addEventListener("hashchange", handleRouting);
  handleRouting();
}

function handleRouting() {
  const hash = window.location.hash || "#/";
  
  // 1. Root route: Landing Page / Site Selection
  if (hash === "#/" || hash === "") {
    const savedSite = localStorage.getItem("pragma-active-site");
    if (savedSite) {
      // Auto-redirect if there is a saved site
      window.location.hash = `#/site/${savedSite}/graph`;
      return;
    }
    loadSitesDashboard();
    return;
  }

  // 2. Site routes: #/site/:site/graph, #/site/:site/lists, #/site/:site/documents, #/site/:site/documents/:name
  const siteMatch = hash.match(/^#\/site\/([^/]+)\/(graph|lists|documents)(?:\/([^/]+))?$/);
  if (siteMatch) {
    const [_, site, page, docName] = siteMatch;
    
    // Save active site
    localStorage.setItem("pragma-active-site", site);
    
    // Initialize shell sidebar (ensure it exists and is updated)
    initShell(page, site);
    
    // Ensure store is loaded with site data
    ensureStoreLoaded(site, () => {
      if (page === "graph") {
        loadGraphView();
      } else if (page === "lists") {
        loadListsView();
      } else if (page === "documents") {
        if (docName) {
          loadDocumentEditorView(site, docName);
        } else {
          loadDocumentsListView(site);
        }
      }
    });
    return;
  }

  // Fallback: Redirect to root
  window.location.hash = "#/";
}

function ensureStoreLoaded(site, callback) {
  if (store.isLoaded && store.filename === site) {
    callback();
    return;
  }

  const container = document.getElementById("app-content");
  container.innerHTML = `
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px;">
      <div style="width: 32px; height: 32px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s infinite linear;"></div>
      <p style="color: var(--text-dim);">Loading graph for <strong>${site}</strong>...</p>
    </div>
    <style>
      @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
  `;

  fetch(`/api/${site}/graph`)
    .then((res) => {
      if (!res.ok) throw new Error("HTTP error " + res.status);
      return res.json();
    })
    .then((data) => {
      store.load(data, site, true);
      // Dispatch graph-loaded event for lists and details compatibility
      document.dispatchEvent(new CustomEvent("graph-loaded"));
      callback();
    })
    .catch((err) => {
      container.innerHTML = `
        <div style="padding: 40px; text-align: center;">
          <h3 style="color: var(--accent); margin-bottom: 12px;">Failed to load graph database</h3>
          <p style="color: var(--text-dim); margin-bottom: 20px;">${err.message}</p>
          <a href="#/" style="display: inline-block; background: var(--border); padding: 8px 16px; border-radius: 4px;">Back to Selection</a>
        </div>
      `;
    });
}

function loadSitesDashboard() {
  const container = document.getElementById("app-content");
  // Hide sidebar on the landing dashboard since there's no active site yet
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.style.display = "none";
  
  container.innerHTML = `
    <div style="max-width: 800px; margin: 80px auto; padding: 0 20px;">
      <h1 style="font-size: 28px; font-weight: 700; margin-bottom: 8px; color: var(--text);">Pragma Hub</h1>
      <p style="color: var(--text-dim); font-size: 15px; margin-bottom: 40px;">Select a crawled site database to explore its architecture, components, and documentation.</p>
      
      <div id="sites-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 20px;">
        <p style="color: var(--text-dim)">Loading discovered sites...</p>
      </div>
    </div>
  `;

  fetch("/api/sites")
    .then((res) => res.json())
    .then((sites) => {
      const grid = document.getElementById("sites-grid");
      if (!sites || sites.length === 0) {
        grid.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 40px; border: 1px dashed var(--border); border-radius: 8px; text-align: center; background: var(--panel);">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 16px; opacity: 0.5;">
              <circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>
            </svg>
            <h4 style="margin: 0 0 8px; color: var(--text);">No sites crawled yet</h4>
            <p style="margin: 0; color: var(--text-dim); font-size: 13px;">Run <code>python cli.py crawl &lt;url&gt;</code> in your terminal to start exploring sites here.</p>
          </div>
        `;
        return;
      }

      grid.innerHTML = sites
        .map(
          (site) => `
          <a href="#/site/${site}/graph" class="site-card" style="
            display: block;
            padding: 24px;
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            text-decoration: none;
            transition: all var(--transition-fast);
          ">
            <h3 style="margin: 0 0 8px; color: var(--text); font-size: 16px; font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${site}</h3>
            <span style="font-size: 11px; color: var(--accent); display: flex; align-items: center; gap: 4px;">
              Explore Graph →
            </span>
          </a>
        `
        )
        .join("");

      // Add hover styles dynamically
      const style = document.createElement("style");
      style.innerHTML = `
        .site-card:hover {
          border-color: var(--accent) !important;
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
          background: var(--panel-2) !important;
        }
      `;
      document.head.appendChild(style);
    })
    .catch((err) => {
      document.getElementById("sites-grid").innerHTML = `
        <p style="color: var(--danger)">Failed to load sites: ${err.message}</p>
      `;
    });
}

function loadGraphView() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.style.display = ""; // Show sidebar
  initGraphPage();
}

function loadListsView() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.style.display = ""; // Show sidebar
  
  const container = document.getElementById("app-content");
  container.innerHTML = `
    <div class="lists-topbar" id="lists-tabs"></div>
    <div class="lists-body">
      <div class="lists-table-area" id="lists-table-area">
        <div class="lists-search-bar" id="lists-search-bar"></div>
        <div id="lists-table-container"></div>
      </div>
      <div class="drawer" id="lists-drawer">
        <div class="drawer-inner" id="lists-detail"></div>
      </div>
    </div>
  `;
  initListsPage();
}

function loadDocumentsListView(site) {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.style.display = "";
  loadDocumentsList(site);
}

function loadDocumentEditorView(site, filename) {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.style.display = "";
  loadDocumentEditor(site, filename);
}
