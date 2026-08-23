"""Static client-side assets for the Graph card (`dashboard/graph_renderer.py`,
ticket #163, map #159) - the CSS, the Cytoscape.js interaction logic, and
ADR-0002's node-type vocabulary. Split out from `graph_renderer.py` itself
(file-size-audit WATCH threshold, `clean-code-principles` SRP check) since
these are data - what the page looks like and how it behaves client-side -
a different reason to change than `graph_renderer.py`'s own job: escaping,
embedding `export.json`'s content safely, assembling the page skeleton.

**Design settled by prototype, not by this ticket.** `docs/prototype-graph-card/`
(throwaway `prototype/graph-card` branch, ticket #162) built and reacted
to five structurally different layouts against real crawl data; the
winner - "Variant E" - is what `SCRIPT` ships, largely unchanged: the page
starts collapsed to the "structural" families (`Pantalla`, `Modulo`), and
clicking a node offers **View details** (a slide-over with a parameter
grid and connections grouped by `export.json`'s real predicate vocabulary)
or **Expand children** (reveals that node's direct neighbors on the same
canvas); **Show all** covers the "I want to see everything" case.

`SCRIPT` carries two placeholders, `__FAMILY_COLORS__`/`__RESERVED_TYPES__`,
substituted by `render_graph_page` with `FAMILY_COLORS`/`RESERVED_TYPES`
below (as real JSON) - the palette is computed once here, not duplicated
in the template string itself.

Details: docs/dev/dashboard/graph_assets.md#module
"""
from __future__ import annotations

SCRIPT_SRC = "https://cdn.jsdelivr.net/npm/cytoscape@3/dist/cytoscape.min.js"

STYLE = """
:root {
  --bg: #0f1115; --panel: #161922; --panel-2: #1c2029; --border: #2a2f3a;
  --text: #e4e7ee; --text-dim: #8b93a7; --accent: #5b8cff; --accent-dim: #2c3a5e;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
a { color: var(--accent); text-decoration: none; }
code { background: var(--panel-2); padding: 1px 5px; border-radius: 4px; font-size: 12px; }

.topbar { display: flex; align-items: center; gap: 16px; padding: 12px 20px; background: var(--panel); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.breadcrumb { color: var(--text-dim); font-size: 13px; }
.breadcrumb a { color: var(--text-dim); }
.topbar h1 { font-size: 15px; margin: 0; }
.search { background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; color: var(--text); font-size: 12px; width: 200px; }
.legend-row { display: flex; gap: 6px; flex-wrap: wrap; }
.view-controls { display: flex; gap: 8px; margin-left: auto; }
.view-btn { background: var(--panel-2); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.view-btn:hover { border-color: var(--accent); }

.swatch { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; flex-shrink: 0; }
.family-pill { display: inline-flex; align-items: center; padding: 3px 10px 3px 8px; border-radius: 999px; border: 1px solid var(--border); background: var(--panel-2); font-size: 11px; cursor: pointer; user-select: none; white-space: nowrap; }
.family-pill.off { opacity: .35; }
.family-pill .count { color: var(--text-dim); margin-left: 5px; }
.family-pill.reserved { border-style: dashed; opacity: .5; cursor: default; }

.body { display: flex; height: calc(100vh - 51px); position: relative; }
.cy-canvas { flex: 1; min-width: 0; background: var(--bg); }
.hint { position: absolute; bottom: 16px; left: 16px; font-size: 11px; color: var(--text-dim); background: rgba(22,25,34,.85); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; z-index: 10; }

.popover { position: absolute; background: #000; border: 1px solid #444; border-radius: 8px; padding: 6px; display: none; z-index: 40; box-shadow: 0 8px 24px rgba(0,0,0,.5); }
.popover.showing { display: flex; gap: 6px; }
.popover button { background: #222; border: none; color: #fff; padding: 6px 12px; border-radius: 5px; cursor: pointer; font-size: 11px; white-space: nowrap; }
.popover button:hover { background: var(--accent); }
.popover button:disabled { opacity: .35; cursor: default; }

.drawer { width: 0; overflow: hidden; flex-shrink: 0; border-left: 1px solid var(--border); background: var(--panel); transition: width .18s ease; }
.drawer.open { width: max(500px, 50vw); }
.drawer-inner { width: 100%; height: 100%; overflow-y: auto; padding: 18px; position: relative; }
.drawer-close { position: absolute; top: 14px; right: 14px; cursor: pointer; color: var(--text-dim); font-size: 18px; }
.type-badge { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 999px; font-weight: 700; margin-bottom: 8px; }
.detail-head h2 { font-size: 18px; margin: 0 0 4px; }
.detail-head .id { font-size: 11px; color: var(--text-dim); word-break: break-all; margin-bottom: 8px; }
.ego-graph { width: 100%; height: 340px; background: var(--bg); border: 1px solid var(--border); border-radius: 10px; margin: 10px 0 2px; }
.ego-caption { text-align: center; font-size: 10px; color: var(--text-dim); margin-bottom: 12px; }
.param-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; padding: 14px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin-bottom: 16px; }
.param-grid .k { font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-dim); margin-bottom: 2px; }
.param-grid .v { font-size: 13px; }
.connected h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-dim); margin: 0 0 10px; }
.connected-group { margin-bottom: 14px; }
.connected-group .pred-label { font-size: 11px; color: var(--text-dim); margin-bottom: 6px; }
.connected-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.connected-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; cursor: pointer; }
.connected-card:hover { border-color: var(--accent); }
.connected-card .name { font-size: 12px; font-weight: 600; }
.connected-card .type { font-size: 10px; color: var(--text-dim); }
"""

# ADR-0002's full node vocabulary. Populated types (real @graph entries
# today) get their own color; reserved types (schemas/export.schema.json's
# `type` enum, not yet emitted by any generator) render dimmed in the
# legend rather than being silently absent - ticket #162's own prototype
# confirmed that reads clearly rather than looking like an omission.
FAMILY_COLORS = {
    "Pantalla": "#5b8cff", "Componente": "#4ade80", "Endpoint": "#fb923c", "Token": "#f472b6",
    "Modulo": "#a78bfa", "Entidad": "#fbbf24", "Requisito": "#22d3ee",
    "Escenario": "#6b7280", "Hallazgo": "#6b7280", "Flujo": "#6b7280", "Estado": "#6b7280",
}
RESERVED_TYPES = ("Escenario", "Hallazgo", "Flujo", "Estado")

SCRIPT = """
const PREDICATES = ["contiene", "navega_a", "dispara", "consume", "usa_token", "depende_de", "implementa", "cubre"];
const PREDICATE_LABELS = {
  contiene: "contains", navega_a: "navigates to", dispara: "triggers",
  consume: "calls", usa_token: "uses token", depende_de: "depends on",
  implementa: "implements", cubre: "covers",
};
const FAMILY_COLORS = __FAMILY_COLORS__;
const RESERVED_TYPES = new Set(__RESERVED_TYPES__);

const EXPORT_DOCUMENT = JSON.parse(document.getElementById("export-data").textContent);
let nodesById = new Map(EXPORT_DOCUMENT["@graph"].map(n => [n.id, n]));

function graphToElements(doc) {
  const elements = [];
  for (const n of nodesById.values()) elements.push({ data: { id: n.id, type: n.type, label: n.label || n.id } });
  let edgeCounter = 0;
  for (const n of nodesById.values()) {
    for (const predicate of PREDICATES) {
      for (const targetId of (n[predicate] || [])) {
        if (!nodesById.has(targetId)) continue; // dangling target, dropped same as graph_export.py itself does
        elements.push({ data: { id: `e${edgeCounter++}`, source: n.id, target: targetId, predicate } });
      }
    }
  }
  return elements;
}

function familyCounts() {
  const counts = {};
  for (const n of nodesById.values()) counts[n.type] = (counts[n.type] || 0) + 1;
  return counts;
}

function nodeEdges(nodeId) {
  const node = nodesById.get(nodeId);
  const outgoing = [], incoming = [];
  for (const predicate of PREDICATES) {
    for (const targetId of (node[predicate] || [])) {
      if (nodesById.has(targetId)) outgoing.push({ predicate, id: targetId });
    }
  }
  for (const other of nodesById.values()) {
    for (const predicate of PREDICATES) {
      if ((other[predicate] || []).includes(nodeId)) incoming.push({ predicate, id: other.id });
    }
  }
  return { outgoing, incoming };
}

// A node's real label (a page title, a component's own rendered text, a
// long #state:-fragment URL) can run far longer than fits legibly next to
// a 22px dot - truncated on the canvas, never on data: the full label
// still shows untruncated in the detail drawer once a node is clicked.
const LABEL_MAX_LENGTH = 26;
function truncateLabel(label) {
  return label.length > LABEL_MAX_LENGTH ? `${label.slice(0, LABEL_MAX_LENGTH - 1)}…` : label;
}

const CY_STYLE = [
  { selector: "node", style: {
      "background-color": ele => FAMILY_COLORS[ele.data("type")] || "#8b93a7",
      "label": ele => truncateLabel(ele.data("label")), "font-size": 9, "color": "#e4e7ee",
      "text-outline-width": 2, "text-outline-color": "#0f1115",
      "width": 22, "height": 22, "text-valign": "bottom", "text-margin-y": 4,
      "min-zoomed-font-size": 7,
  }},
  { selector: "edge", style: {
      "width": 1.4, "line-color": "#3a3f4d", "target-arrow-color": "#3a3f4d",
      "target-arrow-shape": "triangle", "arrow-scale": 0.7, "curve-style": "bezier", "opacity": 0.55,
  }},
  { selector: ".faded", style: { "opacity": 0.06 } },
  { selector: ".hidden-family, .hidden-node", style: { "display": "none" } },
  { selector: ".selected-node", style: { "border-width": 3, "border-color": "#fff", "width": 30, "height": 30 } },
];

// cose's own real default is nodeRepulsion: 400000 - this file previously
// set 9000 (44x weaker), which is the real cause nodes rendered stacked
// directly on top of each other on a real crawl's denser hub cluster
// (several Pantalla nodes sharing many Componente nodes): far too weak a
// repulsive force to push a moderately dense subgraph apart. nodeOverlap
// adds a dedicated post-layout overlap-removal pass on top, for the
// isolated (edge-less) nodes cose's own force simulation alone won't
// necessarily separate. One shared constant, not four separately-tunable
// copies (buildGraph/expandNode/showAllNodes/resetToOverview each ran
// their own layout before this).
const COSE_LAYOUT = { name: "cose", padding: 40, nodeRepulsion: 400000, idealEdgeLength: 90, nodeOverlap: 20 };

function initCy(containerId) {
  return cytoscape({
    container: document.getElementById(containerId),
    elements: graphToElements(),
    style: CY_STYLE,
    layout: { ...COSE_LAYOUT, animate: false },
    minZoom: 0.15, maxZoom: 4,
  });
}

// An edge hides whenever either endpoint is hidden for any reason - a
// family toggled off in the legend, or a node not yet expanded into view.
function isNodeHidden(node) { return node.hasClass("hidden-family") || node.hasClass("hidden-node"); }
function recomputeEdgeVisibility(cy) {
  cy.edges().forEach(e => e.toggleClass("hidden-family", isNodeHidden(e.source()) || isNodeHidden(e.target())));
}

function applySearch(cy, query) {
  const q = query.trim().toLowerCase();
  if (!q) { cy.nodes().removeClass("faded"); return; }
  const matches = cy.nodes().filter(n => n.id().toLowerCase().includes(q) || n.data("label").toLowerCase().includes(q));
  cy.nodes().addClass("faded");
  matches.removeClass("faded");
  if (matches.length) cy.animate({ fit: { eles: matches, padding: 80 } }, { duration: 300 });
}

function selectNode(cy, nodeId) {
  cy.nodes().removeClass("selected-node");
  cy.getElementById(nodeId).addClass("selected-node");
}

function escAttr(s) { return s.replace(/'/g, "\\\\'"); }

// ============================================================
// The detail drawer - a node's own parameter grid, connections grouped
// by export.json's real predicate vocabulary, and a small ego graph
// (just that node and its direct neighbors, capped and captioned).
// ============================================================
const DETAIL_PANEL = { egoContainerId: "ego-graph", egoCaptionId: "ego-caption", jumpFn: "openDetail" };
let egoCy = null;

function renderNodeDetail(nodeId, panel) {
  const node = nodesById.get(nodeId);
  const { outgoing, incoming } = nodeEdges(nodeId);
  panel.detailEl.innerHTML = `
    <span class="type-badge" style="background:${FAMILY_COLORS[node.type]}22;color:${FAMILY_COLORS[node.type]}">${node.type}</span>
    <div class="detail-head">
      <h2>${node.label}</h2>
      <div class="id"><code>${node.id}</code></div>
    </div>
    <div class="ego-graph" id="${panel.egoContainerId}"></div>
    <div class="ego-caption" id="${panel.egoCaptionId}"></div>
    <div class="param-grid">
      <div><div class="k">Type</div><div class="v">${node.type}</div></div>
      <div><div class="k">Total connections</div><div class="v">${outgoing.length + incoming.length}</div></div>
      <div><div class="k">Out-degree</div><div class="v">${outgoing.length}</div></div>
      <div><div class="k">In-degree</div><div class="v">${incoming.length}</div></div>
    </div>
    <div class="connected">
      <h3>Connected elements (${outgoing.length + incoming.length})</h3>
      ${connectedGroupsHtml(outgoing, incoming, panel.jumpFn)}
    </div>
  `;
  renderEgoGraph(nodeId, outgoing, incoming, panel);
}

function connectedGroupsHtml(outgoing, incoming, jumpFn) {
  const groups = {};
  for (const e of outgoing) (groups[PREDICATE_LABELS[e.predicate] || e.predicate] = groups[PREDICATE_LABELS[e.predicate] || e.predicate] || []).push(e.id);
  for (const e of incoming) {
    const label = `${PREDICATE_LABELS[e.predicate] || e.predicate} of`;
    (groups[label] = groups[label] || []).push(e.id);
  }
  if (!Object.keys(groups).length) return `<div style="color:var(--text-dim);font-size:12px">No edges either direction.</div>`;
  return Object.entries(groups).map(([label, ids]) => `
    <div class="connected-group">
      <div class="pred-label">${label} (${ids.length})</div>
      <div class="connected-cards">
        ${ids.map(id => { const n = nodesById.get(id); return `
          <div class="connected-card" onclick="${jumpFn}('${escAttr(id)}')">
            <div class="name">${n.label}</div>
            <div class="type" style="color:${FAMILY_COLORS[n.type]}">${n.type}</div>
          </div>`; }).join("")}
      </div>
    </div>`).join("");
}

function renderEgoGraph(nodeId, outgoing, incoming, panel) {
  if (egoCy) egoCy.destroy();
  const CAP = 10;
  const neighborIds = [...new Set([...outgoing, ...incoming].map(e => e.id))];
  const shown = neighborIds.slice(0, CAP);
  const elements = [{ data: { id: nodeId, type: nodesById.get(nodeId).type, label: nodesById.get(nodeId).label, center: 2 } }];
  for (const id of shown) {
    const n = nodesById.get(id);
    elements.push({ data: { id, type: n.type, label: n.label, center: 1 } });
  }
  let i = 0;
  for (const e of outgoing) if (shown.includes(e.id)) elements.push({ data: { id: `eo${i++}`, source: nodeId, target: e.id } });
  for (const e of incoming) if (shown.includes(e.id)) elements.push({ data: { id: `ei${i++}`, source: e.id, target: nodeId } });

  egoCy = cytoscape({
    container: document.getElementById(panel.egoContainerId),
    elements, style: CY_STYLE,
    layout: { name: "concentric", concentric: n => n.data("center"), levelWidth: () => 1, minNodeSpacing: 40, padding: 20 },
    minZoom: 0.3, maxZoom: 4, boxSelectionEnabled: false,
  });
  egoCy.on("tap", "node", evt => { if (evt.target.id() !== nodeId) window[panel.jumpFn](evt.target.id()); });
  const remaining = neighborIds.length - shown.length;
  document.getElementById(panel.egoCaptionId).textContent = remaining > 0
    ? `${shown.length} connections shown (+${remaining} more below)`
    : `${shown.length} connection${shown.length === 1 ? "" : "s"}`;
}

// ============================================================
// The main canvas - starts collapsed to the structural families, grows
// as the reviewer expands nodes, with a "Show all" escape hatch.
// ============================================================
let cy = null, visibleIds = null, popoverNodeId = null;

function structuralNodeIds() {
  return new Set([...nodesById.values()].filter(n => n.type === "Pantalla" || n.type === "Modulo").map(n => n.id));
}

function buildGraph() {
  visibleIds = structuralNodeIds();
  cy = initCy("cy");
  cy.nodes().forEach(n => n.toggleClass("hidden-node", !visibleIds.has(n.id())));
  recomputeEdgeVisibility(cy);
  cy.layout({ ...COSE_LAYOUT, animate: false }).run();

  const counts = familyCounts();
  document.getElementById("legend").innerHTML = Object.keys(FAMILY_COLORS).map(type => {
    const reserved = RESERVED_TYPES.has(type);
    const count = counts[type] || 0;
    return `<span class="family-pill${reserved ? " reserved" : ""}" data-type="${type}" onclick="${reserved ? "" : `toggleLegendFamily('${type}')`}">
      <span class="swatch" style="background:${FAMILY_COLORS[type]}"></span>${type}<span class="count">${reserved ? "not in this run" : count}</span>
    </span>`;
  }).join("");

  cy.on("tap", "node", evt => showPopover(evt.target.id(), evt.renderedPosition));
  cy.on("tap", evt => { if (evt.target === cy) hidePopover(); });
  cy.on("pan zoom drag", () => hidePopover());
  document.getElementById("search").addEventListener("input", e => applySearch(cy, e.target.value));
  document.getElementById("popover-inspect").addEventListener("click", () => { openDetail(popoverNodeId); hidePopover(); });
  document.getElementById("popover-expand").addEventListener("click", () => { expandNode(popoverNodeId); hidePopover(); });
  updateVisibilityHint();
}

function toggleLegendFamily(type) {
  cy.nodes(`[type = "${type}"]`).toggleClass("hidden-family");
  recomputeEdgeVisibility(cy);
  document.querySelector(`#legend .family-pill[data-type="${type}"]`).classList.toggle("off");
}

function hiddenNeighborCount(nodeId) {
  const { outgoing, incoming } = nodeEdges(nodeId);
  const neighborIds = new Set([...outgoing, ...incoming].map(e => e.id));
  let hidden = 0;
  for (const id of neighborIds) if (!visibleIds.has(id)) hidden++;
  return hidden;
}

function showPopover(nodeId, pos) {
  popoverNodeId = nodeId;
  const hiddenCount = hiddenNeighborCount(nodeId);
  const expandBtn = document.getElementById("popover-expand");
  expandBtn.disabled = hiddenCount === 0;
  expandBtn.textContent = hiddenCount > 0 ? `Expand children (${hiddenCount})` : "Expand children";
  const pop = document.getElementById("popover");
  pop.classList.add("showing");
  pop.style.left = Math.min(pos.x + 12, window.innerWidth - 260) + "px";
  pop.style.top = Math.min(pos.y + 12, window.innerHeight - 60) + "px";
}
function hidePopover() { document.getElementById("popover").classList.remove("showing"); }

function syncVisibility() {
  cy.nodes().forEach(n => n.toggleClass("hidden-node", !visibleIds.has(n.id())));
  recomputeEdgeVisibility(cy);
  updateVisibilityHint();
}

function expandNode(nodeId) {
  const { outgoing, incoming } = nodeEdges(nodeId);
  const neighborIds = new Set([...outgoing, ...incoming].map(e => e.id));
  for (const id of neighborIds) visibleIds.add(id);
  syncVisibility();
  cy.layout({ ...COSE_LAYOUT, animate: false }).run();
  const revealed = cy.nodes().filter(n => neighborIds.has(n.id())).union(cy.getElementById(nodeId));
  if (revealed.length) cy.animate({ fit: { eles: revealed, padding: 100 } }, { duration: 300 });
}

function showAllNodes() {
  visibleIds = new Set(nodesById.keys());
  syncVisibility();
  cy.layout({ ...COSE_LAYOUT, animate: true, animationDuration: 400 }).run();
}

function resetToOverview() {
  visibleIds = structuralNodeIds();
  syncVisibility();
  cy.layout({ ...COSE_LAYOUT, animate: true, animationDuration: 400 }).run();
  closeDrawer();
}

function updateVisibilityHint() {
  const total = nodesById.size, visible = visibleIds.size;
  document.getElementById("hint").textContent = visible < total
    ? `Showing ${visible} of ${total} nodes \\u2014 click a node, then "Expand children", or "Show all".`
    : `Showing all ${total} nodes.`;
}

function openDetail(nodeId) {
  if (!visibleIds.has(nodeId)) { visibleIds.add(nodeId); syncVisibility(); }
  selectNode(cy, nodeId);
  const drawer = document.getElementById("drawer");
  const alreadyOpen = drawer.classList.contains("open");
  // Open the drawer BEFORE rendering the ego-graph into it - cytoscape
  // reads its container's real dimensions at construction time, and a
  // still-closed (width: 0) drawer would size it wrong. When the drawer
  // is opening fresh, its own CSS width transition still has to finish
  // first - resize/fit once that transition really ends, not just next
  // frame (the transition takes 180ms, well past one frame).
  drawer.classList.add("open");
  renderNodeDetail(nodeId, { detailEl: document.getElementById("detail"), ...DETAIL_PANEL });
  if (alreadyOpen) {
    if (egoCy) requestAnimationFrame(() => { egoCy.resize(); egoCy.fit(undefined, 20); });
  } else {
    drawer.addEventListener("transitionend", function onOpen(e) {
      if (e.propertyName !== "width") return;
      drawer.removeEventListener("transitionend", onOpen);
      if (egoCy) { egoCy.resize(); egoCy.fit(undefined, 20); }
    });
  }
}
function closeDrawer() { document.getElementById("drawer").classList.remove("open"); }

buildGraph();
"""
