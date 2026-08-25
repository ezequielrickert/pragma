/**
 * Documents Page — List and Editor views for crawled files.
 */

import { store } from "../graph-store.js";
import { initShell } from "../layout/shell.js";

// Helper to escape HTML safely
function escHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Render the documents list view.
 */
export function loadDocumentsList(site) {
  const container = document.getElementById("app-content");
  
  container.innerHTML = `
    <div style="padding: 40px; max-width: 900px; margin: 0 auto; height: 100%; overflow-y: auto;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px;">
        <div>
          <h1 style="font-size: 26px; font-weight: 700; color: var(--text); margin: 0 0 6px;">Crawled Documents</h1>
          <p style="color: var(--text-dim); margin: 0; font-size: 14px;">Select a document below to view its contents, analyze details, or edit overrides.</p>
        </div>
        <a href="#/site/${site}/graph" style="background: var(--panel-2); border: 1px solid var(--border); padding: 8px 16px; border-radius: var(--radius-md); font-size: 13px; text-decoration: none; color: var(--text);">← Back to Graph</a>
      </div>
      
      <div id="docs-list-container" style="background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;">
        <table class="node-table" style="width: 100%; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="border-bottom: 1px solid var(--border); background: var(--panel-2);">
              <th style="padding: 14px 20px; font-weight: 600; font-size: 13px; color: var(--text-dim);">Document Name</th>
              <th style="padding: 14px 20px; font-weight: 600; font-size: 13px; color: var(--text-dim);">Format</th>
              <th style="padding: 14px 20px; font-weight: 600; font-size: 13px; color: var(--text-dim);">Status</th>
              <th style="padding: 14px 20px; font-weight: 600; font-size: 13px; color: var(--text-dim); text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="docs-tbody">
            <tr>
              <td colspan="4" style="padding: 24px; text-align: center; color: var(--text-dim);">Loading documents list...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  fetch(`/api/${site}/documents`)
    .then((res) => {
      if (!res.ok) throw new Error("HTTP error " + res.status);
      return res.json();
    })
    .then((docs) => {
      const tbody = document.getElementById("docs-tbody");
      if (!docs || docs.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="4" style="padding: 32px; text-align: center; color: var(--text-dim);">No documents found for this site.</td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = docs
        .map((doc) => {
          const fullName = `${doc.filename}.${doc.extension}`;
          const statusBadge = doc.customized
            ? `<span style="background: rgba(34, 197, 94, 0.15); color: #22c55e; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid rgba(34, 197, 94, 0.3);">Modified</span>`
            : `<span style="background: rgba(255, 255, 255, 0.05); color: var(--text-dim); padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid var(--border);">Original</span>`;
            
          return `
            <tr style="border-bottom: 1px solid var(--border);" class="doc-row">
              <td style="padding: 16px 20px; font-weight: 500; color: var(--text);">${fullName}</td>
              <td style="padding: 16px 20px; color: var(--text-dim); font-size: 13px;">${doc.extension.toUpperCase()}</td>
              <td style="padding: 16px 20px;">${statusBadge}</td>
              <td style="padding: 16px 20px; text-align: right;">
                <a href="#/site/${site}/documents/${fullName}" class="graph-btn" style="text-decoration: none; display: inline-block;">View / Edit</a>
              </td>
            </tr>
          `;
        })
        .join("");

      // Add dynamic hover styles for rows
      const style = document.createElement("style");
      style.innerHTML = `
        .doc-row:hover {
          background: rgba(255, 255, 255, 0.02);
        }
      `;
      document.head.appendChild(style);
    })
    .catch((err) => {
      document.getElementById("docs-tbody").innerHTML = `
        <tr>
          <td colspan="4" style="padding: 24px; text-align: center; color: var(--danger);">Failed to load documents: ${err.message}</td>
        </tr>
      `;
    });
}

/**
 * Render the document view/edit screen.
 */
export function loadDocumentEditor(site, docFullName) {
  const container = document.getElementById("app-content");
  
  // Set up loading view
  container.innerHTML = `
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px;">
      <div style="width: 32px; height: 32px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s infinite linear;"></div>
      <p style="color: var(--text-dim);">Opening <strong>${docFullName}</strong>...</p>
    </div>
  `;

  fetch(`/api/${site}/documents/${docFullName}`)
    .then((res) => {
      if (!res.ok) throw new Error("HTTP error " + res.status);
      return res.json();
    })
    .then((doc) => {
      renderEditorLayout(container, site, docFullName, doc);
    })
    .catch((err) => {
      container.innerHTML = `
        <div style="padding: 40px; text-align: center;">
          <h3 style="color: var(--accent); margin-bottom: 12px;">Failed to load document</h3>
          <p style="color: var(--text-dim); margin-bottom: 20px;">${err.message}</p>
          <a href="#/site/${site}/documents" class="graph-btn" style="text-decoration: none;">Back to Documents</a>
        </div>
      `;
    });
}

function renderEditorLayout(container, site, docFullName, doc) {
  const hasForm = doc.filename === "tokens" || doc.has_schema;
  let activeTab = "edit"; // default tab
  
  container.innerHTML = `
    <div class="doc-editor-shell" style="display: flex; flex-direction: column; height: 100%; background: #0b0c10;">
      <!-- Editor Header -->
      <div class="editor-header" style="display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--panel);">
        <div style="display: flex; align-items: center; gap: 16px;">
          <a href="#/site/${site}/documents" class="graph-btn" style="text-decoration: none; display: flex; align-items: center; gap: 6px;">
            ← Documents
          </a>
          <h2 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text);">${docFullName}</h2>
          <span id="save-status-badge" style="font-size: 11px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); padding: 4px 8px; border-radius: 4px; color: var(--text-dim);">Saved</span>
        </div>
        
        <div style="display: flex; align-items: center; gap: 16px;">
          <!-- Tab toggles -->
          <div class="tab-toggle-group" style="display: flex; background: var(--panel-2); border: 1px solid var(--border); padding: 2px; border-radius: var(--radius-md);">
            <button id="toggle-view-tab" class="tab-toggle-btn" style="padding: 6px 16px; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; background: transparent; color: var(--text-dim);">View</button>
            <button id="toggle-edit-tab" class="tab-toggle-btn active" style="padding: 6px 16px; border: none; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; cursor: pointer; background: var(--panel); color: var(--text); border: 1px solid var(--border);">Edit</button>
          </div>
          
          <button id="btn-save-document" class="graph-btn" style="background: var(--accent); color: white; border: none;">Save Changes</button>
        </div>
      </div>
      
      <!-- Alert bar for schema validation errors -->
      <div id="validation-alert-bar" style="display: none; background: rgba(239, 68, 68, 0.15); border-bottom: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; padding: 12px 24px; font-size: 13px; font-weight: 500;">
      </div>

      <!-- Editor Content Panes -->
      <div class="editor-panes-container" style="display: flex; flex: 1; min-height: 0;">
        <!-- Left Pane: Text Editor -->
        <div class="editor-pane-left" style="flex: 1; display: flex; flex-direction: column; border-right: 1px solid var(--border); min-width: 0;">
          <div style="display: flex; flex: 1; min-height: 0; position: relative;">
            <div id="editor-gutter" style="
              width: 48px; 
              background: #0d0e12; 
              color: rgba(255,255,255,0.2); 
              font-family: monospace; 
              font-size: 13px; 
              text-align: right; 
              padding: 16px 8px 16px 0; 
              user-select: none; 
              border-right: 1px solid rgba(255,255,255,0.03);
              line-height: 1.5;
              overflow: hidden;
            "></div>
            <textarea id="editor-textarea" style="
              flex: 1; 
              background: transparent; 
              color: var(--text); 
              border: none; 
              resize: none; 
              outline: none; 
              font-family: monospace; 
              font-size: 13px; 
              line-height: 1.5; 
              padding: 16px; 
              overflow-y: auto;
              white-space: pre;
            ">${escHtml(doc.content || "")}</textarea>
          </div>
        </div>

        <!-- Middle/Right Pane: Forms Overrides or Preview -->
        <div id="editor-pane-right" style="flex: 1; display: flex; flex-direction: column; background: #0f1115; min-width: 0; overflow-y: auto; padding: 24px;">
          <!-- Content dynamically rendered by updateRightPane() -->
        </div>
      </div>
    </div>
  `;

  const textarea = document.getElementById("editor-textarea");
  const gutter = document.getElementById("editor-gutter");
  const saveBtn = document.getElementById("btn-save-document");
  const saveStatus = document.getElementById("save-status-badge");
  const alertBar = document.getElementById("validation-alert-bar");
  const rightPane = document.getElementById("editor-pane-right");
  const viewTabBtn = document.getElementById("toggle-view-tab");
  const editTabBtn = document.getElementById("toggle-edit-tab");

  let isDirty = false;
  let parsedJson = null;

  // Gutter update logic
  function updateGutter() {
    const lines = textarea.value.split("\n").length;
    gutter.innerHTML = Array.from({ length: lines }, (_, i) => `<div>${i + 1}</div>`).join("");
  }

  textarea.addEventListener("scroll", () => {
    gutter.scrollTop = textarea.scrollTop;
  });

  // Track changes and mark as dirty
  textarea.addEventListener("input", () => {
    isDirty = true;
    saveStatus.textContent = "Unsaved Changes";
    saveStatus.style.borderColor = "var(--accent)";
    saveStatus.style.color = "var(--accent)";
    updateGutter();
    tryParseJson();
    updateRightPane();
  });

  // JSON parsing and form sync
  function tryParseJson() {
    if (doc.extension === "json") {
      try {
        parsedJson = JSON.parse(textarea.value);
        alertBar.style.display = "none";
      } catch (e) {
        parsedJson = null; // invalid JSON
      }
    }
  }

  // Initial parses
  updateGutter();
  tryParseJson();

  // Tab Toggle Logic
  viewTabBtn.addEventListener("click", () => {
    activeTab = "view";
    viewTabBtn.className = "tab-toggle-btn active";
    viewTabBtn.style.background = "var(--panel)";
    viewTabBtn.style.color = "var(--text)";
    viewTabBtn.style.border = "1px solid var(--border)";
    
    editTabBtn.className = "tab-toggle-btn";
    editTabBtn.style.background = "transparent";
    editTabBtn.style.color = "var(--text-dim)";
    editTabBtn.style.border = "none";
    
    updateRightPane();
  });

  editTabBtn.addEventListener("click", () => {
    activeTab = "edit";
    editTabBtn.className = "tab-toggle-btn active";
    editTabBtn.style.background = "var(--panel)";
    editTabBtn.style.color = "var(--text)";
    editTabBtn.style.border = "1px solid var(--border)";
    
    viewTabBtn.className = "tab-toggle-btn";
    viewTabBtn.style.background = "transparent";
    viewTabBtn.style.color = "var(--text-dim)";
    viewTabBtn.style.border = "none";
    
    updateRightPane();
  });

  // Right pane rendering
  function updateRightPane() {
    if (activeTab === "view") {
      renderViewMode();
    } else {
      renderEditMode();
    }
  }

  function renderViewMode() {
    if (doc.extension === "md") {
      rightPane.innerHTML = `
        <div class="markdown-preview" style="color: var(--text); line-height: 1.6; font-size: 14px;">
          ${renderMarkdown(textarea.value)}
        </div>
      `;
    } else if (docFullName === "openapi.yaml" || docFullName === "openapi.json") {
      rightPane.innerHTML = `
        <div id="redoc-container">Loading OpenAPI specs...</div>
      `;
      loadReDoc();
    } else {
      // Default view mode: Side-by-side diff comparing original and current
      rightPane.innerHTML = `
        <h4 style="margin: 0 0 16px; color: var(--text-dim); font-size: 13px; font-weight: 600;">Diff: Original vs Current</h4>
        <div style="overflow-x: auto; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-md);">
          ${renderDiff(doc.original, textarea.value)}
        </div>
      `;
    }
  }

  function renderEditMode() {
    if (doc.filename === "tokens" && doc.extension === "json") {
      if (parsedJson) {
        const colors = findColors(parsedJson);
        rightPane.innerHTML = `
          <h4 style="margin: 0 0 16px; color: var(--text); font-size: 14px; font-weight: 600;">Interactive Design Tokens</h4>
          <div style="display: flex; flex-direction: column; gap: 14px;">
            ${colors.map((c) => `
              <div class="token-field-row" style="display: flex; align-items: center; justify-content: space-between; background: var(--panel); border: 1px solid var(--border); padding: 12px; border-radius: var(--radius-md);">
                <span style="font-family: monospace; font-size: 12px; color: var(--text-dim);">${c.path.join(".")}</span>
                <input type="color" class="token-color-picker" data-path="${c.path.join(".")}" value="${c.value}" style="border: none; background: transparent; cursor: pointer; width: 32px; height: 32px;" />
              </div>
            `).join("")}
          </div>
        `;
        
        // Listen to color changes
        rightPane.querySelectorAll(".token-color-picker").forEach((picker) => {
          picker.addEventListener("input", (e) => {
            const pathStr = e.target.getAttribute("data-path");
            const val = e.target.value;
            updateColorValue(parsedJson, pathStr.split("."), val);
            textarea.value = JSON.stringify(parsedJson, null, 2);
            isDirty = true;
            saveStatus.textContent = "Unsaved Changes";
            saveStatus.style.borderColor = "var(--accent)";
            saveStatus.style.color = "var(--accent)";
            updateGutter();
          });
        });
      } else {
        rightPane.innerHTML = `
          <div style="text-align: center; color: var(--danger); padding: 24px;">
            Invalid JSON syntax. Fix syntax errors in the editor to enable color pickers.
          </div>
        `;
      }
    } else if (doc.has_schema && doc.filename === "requirements") {
      if (parsedJson && parsedJson.requirements) {
        rightPane.innerHTML = `
          <h4 style="margin: 0 0 16px; color: var(--text); font-size: 14px; font-weight: 600;">Interactive Review Form</h4>
          <div style="display: flex; flex-direction: column; gap: 16px;">
            ${parsedJson.requirements.map((req, idx) => `
              <div style="background: var(--panel); border: 1px solid var(--border); padding: 16px; border-radius: var(--radius-md);">
                <div style="font-weight: 600; font-size: 13px; color: var(--accent); margin-bottom: 12px;">${req.id || `Requirement ${idx + 1}`}</div>
                <div style="font-size: 12px; color: var(--text-dim); margin-bottom: 12px; font-style: italic;">"${req.syntax_text}"</div>
                
                <div style="display: flex; flex-direction: column; gap: 10px;">
                  <div style="display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size: 11px; color: var(--text-dim); font-weight: 600;">Hitl Status</label>
                    <select class="req-field-select" data-index="${idx}" data-field="hitl_status" style="background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 6px; border-radius: var(--radius-sm); font-size: 12px;">
                      <option value="unreviewed" ${req.hitl_status === "unreviewed" ? "selected" : ""}>Unreviewed</option>
                      <option value="approved" ${req.hitl_status === "approved" ? "selected" : ""}>Approved</option>
                      <option value="rejected" ${req.hitl_status === "rejected" ? "selected" : ""}>Rejected</option>
                    </select>
                  </div>
                  <div style="display: flex; flex-direction: column; gap: 4px;">
                    <label style="font-size: 11px; color: var(--text-dim); font-weight: 600;">Open Questions</label>
                    <textarea class="req-field-textarea" data-index="${idx}" data-field="open_questions" style="background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 6px; border-radius: var(--radius-sm); font-size: 12px; font-family: sans-serif; resize: vertical; min-height: 50px;">${(req.open_questions || []).join("\n")}</textarea>
                  </div>
                </div>
              </div>
            `).join("")}
          </div>
        `;

        // Listen to field changes
        rightPane.querySelectorAll(".req-field-select, .req-field-textarea").forEach((el) => {
          el.addEventListener("input", (e) => {
            const idx = parseInt(e.target.getAttribute("data-index"));
            const field = e.target.getAttribute("data-field");
            const val = e.target.value;
            
            if (field === "open_questions") {
              parsedJson.requirements[idx][field] = val.split("\n").map(q => q.trim()).filter(Boolean);
            } else {
              parsedJson.requirements[idx][field] = val;
            }

            textarea.value = JSON.stringify(parsedJson, null, 2);
            isDirty = true;
            saveStatus.textContent = "Unsaved Changes";
            saveStatus.style.borderColor = "var(--accent)";
            saveStatus.style.color = "var(--accent)";
            updateGutter();
          });
        });
      } else {
        rightPane.innerHTML = `
          <div style="text-align: center; color: var(--danger); padding: 24px;">
            Invalid JSON syntax. Fix syntax errors in the editor to enable review forms.
          </div>
        `;
      }
    } else {
      // Default edit mode: Live diff showing changes against original on the right
      rightPane.innerHTML = `
        <h4 style="margin: 0 0 16px; color: var(--text-dim); font-size: 13px; font-weight: 600;">Live Diff: Changes against Original</h4>
        <div style="overflow-x: auto; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-md);">
          ${renderDiff(doc.original, textarea.value)}
        </div>
      `;
    }
  }

  // Load ReDoc script and render
  function loadReDoc() {
    if (typeof Redoc === "undefined") {
      const script = document.createElement("script");
      script.src = "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js";
      script.onload = () => initReDoc();
      document.head.appendChild(script);
    } else {
      initReDoc();
    }
  }

  function initReDoc() {
    const el = document.getElementById("redoc-container");
    if (!el) return;
    try {
      let specObj;
      if (doc.extension === "yaml" || doc.extension === "yml") {
        // Basic yaml-to-json parser if we need or just use raw content if Redoc supports YAML
        specObj = textarea.value; // Redoc supports URL, JSON object or YAML string directly
      } else {
        specObj = JSON.parse(textarea.value);
      }
      Redoc.init(specObj, {
        theme: { colors: { primary: { main: "#3b82f6" } } }
      }, el);
    } catch (e) {
      el.innerHTML = `<div style="color:var(--danger)">YAML/JSON syntax error: ${e.message}</div>`;
    }
  }

  // Save changes event handler
  saveBtn.addEventListener("click", () => {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    alertBar.style.display = "none";
    
    fetch(`/api/${site}/documents/${docFullName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: textarea.value })
    })
      .then(async (res) => {
        const resData = await res.json();
        if (res.status === 400 || !resData.success) {
          throw { isValidationError: true, message: resData.error || "Validation failed", path: resData.error_path };
        }
        if (!res.ok) throw new Error("HTTP error " + res.status);
        return resData;
      })
      .then(() => {
        isDirty = false;
        doc.content = textarea.value;
        saveStatus.textContent = "Saved";
        saveStatus.style.borderColor = "var(--border)";
        saveStatus.style.color = "var(--text-dim)";
        
        // Temporarily change button to show success
        saveBtn.style.background = "#22c55e";
        saveBtn.textContent = "Saved ✓";
        setTimeout(() => {
          saveBtn.disabled = false;
          saveBtn.style.background = "var(--accent)";
          saveBtn.textContent = "Save Changes";
        }, 1500);

        tryParseJson();
        updateRightPane();
      })
      .catch((err) => {
        saveBtn.disabled = false;
        saveBtn.style.background = "var(--accent)";
        saveBtn.textContent = "Save Changes";
        
        if (err.isValidationError) {
          alertBar.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <strong>Validation Error:</strong>
              <span>${escHtml(err.message)}</span>
              ${err.path && err.path.length > 0 ? `<span style="font-size: 11px; opacity: 0.8; font-family: monospace;">Path: ${err.path.join(".")}</span>` : ""}
            </div>
          `;
          alertBar.style.display = "block";
        } else {
          alert("Error saving document: " + err.message);
        }
      });
  });

  // Initial draw
  updateRightPane();
}

/**
 * Traverses an object recursively to find Design Tokens of type "color".
 */
function findColors(obj, path = []) {
  const results = [];
  if (!obj || typeof obj !== "object") return results;
  if (obj["$type"] === "color") {
    results.push({ path, value: obj["$value"] });
    return results;
  }
  for (const [key, val] of Object.entries(obj)) {
    results.push(...findColors(val, [...path, key]));
  }
  return results;
}

/**
 * Updates a specific color token value inside the tokens object tree.
 */
function updateColorValue(obj, path, newValue) {
  let current = obj;
  for (let i = 0; i < path.length; i++) {
    if (i === path.length - 1) {
      if (current[path[i]]) {
        current[path[i]]["$value"] = newValue;
      }
    } else {
      current = current[path[i]];
    }
  }
}

/**
 * Basic line-by-line diff generator helper.
 */
function renderDiff(originalText, currentText) {
  const origLines = (originalText || "").split("\n");
  const currLines = (currentText || "").split("\n");
  
  let html = `<table style="width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; line-height: 1.5; background: #0a0b0d;">`;
  const maxLines = Math.max(origLines.length, currLines.length);
  
  for (let i = 0; i < maxLines; i++) {
    const orig = origLines[i] !== undefined ? origLines[i] : "";
    const curr = currLines[i] !== undefined ? currLines[i] : "";
    
    let leftBg = "";
    let rightBg = "";
    let leftColor = "var(--text-dim)";
    let rightColor = "var(--text)";
    let sign = " ";
    
    if (orig !== curr) {
      if (orig && !curr) {
        leftBg = "rgba(239, 68, 68, 0.15)";
        leftColor = "#ef4444";
        sign = "-";
      } else if (!orig && curr) {
        rightBg = "rgba(34, 197, 94, 0.15)";
        rightColor = "#22c55e";
        sign = "+";
      } else {
        leftBg = "rgba(239, 68, 68, 0.1)";
        leftColor = "#ef4444";
        rightBg = "rgba(34, 197, 94, 0.1)";
        rightColor = "#22c55e";
        sign = "M";
      }
    }
    
    html += `
      <tr style="border-bottom: 1px solid rgba(255,255,255,0.01);">
        <td style="width: 32px; text-align: right; padding-right: 8px; color: rgba(255,255,255,0.15); user-select: none; border-right: 1px solid rgba(255,255,255,0.03); background: #0e0f12;">${i + 1}</td>
        <td style="padding: 2px 12px; white-space: pre-wrap; background: ${leftBg}; color: ${leftColor};">${escHtml(orig)}</td>
        <td style="width: 32px; text-align: right; padding-right: 8px; color: rgba(255,255,255,0.15); user-select: none; border-right: 1px solid rgba(255,255,255,0.03); background: #0e0f12;">${i + 1}</td>
        <td style="padding: 2px 12px; white-space: pre-wrap; background: ${rightBg}; color: ${rightColor};">${escHtml(curr)}</td>
      </tr>
    `;
  }
  
  html += `</table>`;
  return html;
}

/**
 * Basic markdown parser helper.
 */
function renderMarkdown(md) {
  if (!md) return "";
  let html = escHtml(md);
  
  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3 style="color: var(--text); font-size: 15px; margin-top: 16px; margin-bottom: 8px; font-weight: 600;">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 style="color: var(--text); font-size: 18px; margin-top: 24px; margin-bottom: 12px; font-weight: 600; border-bottom: 1px solid var(--border); padding-bottom: 6px;">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 style="color: var(--text); font-size: 22px; margin-top: 0; margin-bottom: 16px; font-weight: 700;">$1</h1>');
  
  // Unordered Lists
  html = html.replace(/^\- (.*$)/gim, '<li style="margin-left: 20px; margin-bottom: 6px; color: var(--text);">$1</li>');
  
  // Bold / Italic
  html = html.replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>');
  html = html.replace(/\*(.*)\*/gim, '<em>$1</em>');
  
  // Code blocks
  html = html.replace(/`([^`]+)`/gim, '<code style="background: var(--panel-2); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px;">$1</code>');
  
  // Paragraphs (split by double line breaks)
  const paragraphs = html.split(/\n\n+/);
  return paragraphs
    .map(p => {
      p = p.trim();
      if (!p) return "";
      if (p.startsWith("<h") || p.startsWith("<li") || p.startsWith("<ul")) return p;
      return `<p style="margin-bottom: 14px; color: var(--text-dim);">$p = ${p}</p>`.replace("$p = ", "");
    })
    .join("\n");
}
