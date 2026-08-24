/**
 * NodeDetail — renders a node's full detail panel.
 *
 * Used identically by both the Graph page (in its slide-over drawer)
 * and the Lists page (in its detail panel). Shows:
 * - Type badge (colored)
 * - Node id and label
 * - All raw JSON attributes (not edge predicates)
 * - Edges grouped by predicate, each target as a clickable link
 * - Confidence badge (graceful degradation if absent)
 * - Breadcrumb navigation history
 */

import { store } from "./graph-store.js";
import { selectionState } from "./selection-state.js";
import {
  PREDICATES,
  PREDICATE_LABELS,
  FAMILY_COLORS,
  colorForType,
  typeBadgeHtml,
  nodeBadgeHtml,
} from "./color-palette.js";

/**
 * Render the detail panel for a node into a container element.
 * @param {string} nodeId
 * @param {HTMLElement} container
 */
export function renderNodeDetail(nodeId, container) {
  const node = store.getNode(nodeId);
  if (!node) {
    container.innerHTML = `<div class="detail-empty">Node not found: <code>${escHtml(nodeId)}</code></div>`;
    return;
  }

  const { outgoing, incoming } = store.getEdges(nodeId);
  const rawAttrs = store.getRawAttributes(nodeId);

  container.innerHTML = `
    <div class="detail-header">
      <button class="detail-close" onclick="this.closest('.drawer').classList.remove('open')" title="Close">✕</button>
      ${renderBreadcrumb()}
      ${nodeBadgeHtml(node)}
      <h2 class="detail-title">${escHtml(node.label || node.id)}</h2>
      <div class="detail-id"><code>${escHtml(node.id)}</code></div>
      ${renderConfidence(node)}
    </div>

    <div class="detail-section">
      <h3>Raw Attributes</h3>
      <div class="attr-grid">
        ${renderAttributes(rawAttrs)}
      </div>
    </div>

    <div class="detail-section">
      <h3>Connections <span class="count-badge">${outgoing.length + incoming.length}</span></h3>
      <div class="detail-stats-row">
        <span class="stat-chip">↗ Out: ${outgoing.length}</span>
        <span class="stat-chip">↙ In: ${incoming.length}</span>
      </div>
      ${renderEdgeGroups(outgoing, incoming)}
    </div>
  `;
}

/** Render breadcrumb from navigation history. */
function renderBreadcrumb() {
  const history = selectionState.history;
  if (history.length === 0) return "";

  // Show last 4 items max
  const visible = history.slice(-4);
  const crumbs = visible.map((id) => {
    const node = store.getNode(id);
    const label = node ? (node.label || node.id) : id;
    const truncated = label.length > 20 ? label.slice(0, 19) + "…" : label;
    return `<a href="#" class="breadcrumb-link" data-node-id="${escAttr(id)}" title="${escAttr(label)}">${escHtml(truncated)}</a>`;
  });

  return `
    <nav class="breadcrumb">
      ${history.length > 4 ? '<span class="breadcrumb-ellipsis">…</span>' : ""}
      ${crumbs.join('<span class="breadcrumb-sep">›</span>')}
      <span class="breadcrumb-sep">›</span>
      <span class="breadcrumb-current">current</span>
    </nav>
  `;
}

/** Render confidence badge if the node has confidence data. */
function renderConfidence(node) {
  if (!node.confidence) return "";
  const level = typeof node.confidence === "string" ? node.confidence : node.confidence.level;
  if (!level) return "";

  const colors = {
    observed: "#4ade80",
    inferred: "#fbbf24",
    assumed: "#f87171",
  };
  const color = colors[level] || "#6b7280";

  let derivedHtml = "";
  const derivedFrom = node.confidence?.derived_from;
  if (Array.isArray(derivedFrom) && derivedFrom.length > 0) {
    derivedHtml = `
      <div class="derived-from">
        <span class="derived-label">Evidence:</span>
        ${derivedFrom.map((ref) => `<code class="evidence-ref">${escHtml(ref)}</code>`).join("")}
      </div>
    `;
  }

  return `
    <div class="confidence-row">
      <span class="confidence-badge" style="background:${color}22;color:${color};border:1px solid ${color}44">
        ${level}
      </span>
      ${derivedHtml}
    </div>
  `;
}

/** Render raw attributes as a key-value grid. */
function renderAttributes(attrs) {
  const entries = Object.entries(attrs);
  if (entries.length === 0) return '<div class="attr-empty">No additional attributes</div>';

  return entries
    .map(([key, value]) => {
      const displayValue = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
      const isLong = displayValue.length > 80;
      return `
        <div class="attr-row">
          <div class="attr-key">${escHtml(key)}</div>
          <div class="attr-value${isLong ? " attr-long" : ""}">
            ${isLong ? `<pre>${escHtml(displayValue)}</pre>` : `<span>${escHtml(displayValue)}</span>`}
          </div>
        </div>
      `;
    })
    .join("");
}

/** Render edges grouped by predicate, with clickable targets. */
function renderEdgeGroups(outgoing, incoming) {
  // Group outgoing by predicate
  const outGroups = {};
  for (const edge of outgoing) {
    const label = PREDICATE_LABELS[edge.predicate] || edge.predicate;
    (outGroups[label] = outGroups[label] || []).push(edge.target);
  }

  // Group incoming by predicate
  const inGroups = {};
  for (const edge of incoming) {
    const label = `${PREDICATE_LABELS[edge.predicate] || edge.predicate} (← inbound)`;
    (inGroups[label] = inGroups[label] || []).push(edge.source);
  }

  const allGroups = { ...outGroups, ...inGroups };
  if (Object.keys(allGroups).length === 0) {
    return '<div class="no-edges">No connections</div>';
  }

  return Object.entries(allGroups)
    .map(([label, nodeIds]) => {
      const cards = nodeIds
        .map((id) => {
          const targetNode = store.getNode(id);
          if (!targetNode) return "";
          const color = FAMILY_COLORS[targetNode.type] || "#6b7280";
          const subType = targetNode.tag || targetNode.role || targetNode.category || targetNode.method || targetNode.type_property || targetNode.type;
          return `
            <div class="edge-card" data-node-id="${escAttr(id)}" title="${escAttr(targetNode.label || id)}">
              <div class="edge-card-name">${escHtml(targetNode.label || id)}</div>
              <div class="edge-card-type" style="color:${color}">${subType}</div>
            </div>
          `;
        })
        .join("");

      return `
        <div class="edge-group">
          <div class="edge-group-label">${escHtml(label)} <span class="count-badge">${nodeIds.length}</span></div>
          <div class="edge-cards">${cards}</div>
        </div>
      `;
    })
    .join("");
}

/** Escape HTML entities. */
function escHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

/** Escape for use in HTML attributes. */
function escAttr(str) {
  return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;");
}

/**
 * Attach click handlers for edge cards and breadcrumb links inside a container.
 * Call this after rendering detail into a container.
 * @param {HTMLElement} container
 */
export function attachDetailClickHandlers(container) {
  // Edge card clicks → navigate to that node
  container.querySelectorAll(".edge-card[data-node-id]").forEach((card) => {
    card.addEventListener("click", () => {
      selectionState.select(card.dataset.nodeId);
    });
  });

  // Breadcrumb link clicks → go back to that node
  container.querySelectorAll(".breadcrumb-link[data-node-id]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      selectionState.select(link.dataset.nodeId);
    });
  });
}
