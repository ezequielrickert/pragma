/**
 * GraphStore — data layer for a single export.json snapshot.
 *
 * Parses the `@graph` array into indexed maps for fast lookup.
 * Designed as a single-snapshot class: a future diff-between-runs
 * mode would instantiate two GraphStores and compare them, without
 * touching this class at all.
 *
 * Emits a "loaded" CustomEvent on `document` when new data is parsed.
 */

import { PREDICATES } from "./color-palette.js";

export class GraphStore {
  constructor() {
    /** @type {Map<string, object>} node id → node object */
    this.nodesById = new Map();
    /** @type {Map<string, object[]>} node type → node objects */
    this.nodesByType = new Map();
    /** @type {{ source: string, target: string, predicate: string }[]} */
    this.edges = [];
    /** @type {Map<string, { outgoing: object[], incoming: object[] }>} */
    this.edgeIndex = new Map();
    /** @type {object|null} raw parsed JSON */
    this.rawDocument = null;
    /** @type {string} */
    this.filename = "";

    this.restoreFromSession();
  }

  /** Restore graph from sessionStorage if present. */
  restoreFromSession() {
    try {
      const savedDoc = sessionStorage.getItem("pragma-graph-explorer-raw-data");
      const savedFilename = sessionStorage.getItem("pragma-graph-explorer-filename");
      if (savedDoc) {
        const doc = JSON.parse(savedDoc);
        this.load(doc, savedFilename || "", false);
      }
    } catch (e) {
      console.error("Failed to restore graph store from sessionStorage", e);
    }
  }

  /**
   * Load and index an export.json document.
   * @param {object} doc - Parsed JSON object with `@graph` array
   * @param {string} [filename=""] - Source filename for display
   * @param {boolean} [persist=true] - Whether to save to sessionStorage
   */
  load(doc, filename = "", persist = true) {
    this.rawDocument = doc;
    this.filename = filename;
    
    if (persist) {
      try {
        sessionStorage.setItem("pragma-graph-explorer-raw-data", JSON.stringify(doc));
        sessionStorage.setItem("pragma-graph-explorer-filename", filename);
      } catch (e) {
        console.error("Failed to save graph store to sessionStorage", e);
      }
    }

    this.nodesById.clear();
    this.nodesByType.clear();
    this.edges = [];
    this.edgeIndex.clear();

    const graph = doc["@graph"] || [];

    // Index nodes
    for (const node of graph) {
      this.nodesById.set(node.id, node);
      const typeList = this.nodesByType.get(node.type) || [];
      typeList.push(node);
      this.nodesByType.set(node.type, typeList);
    }

    // Build edge list and index
    for (const node of graph) {
      const outgoing = [];
      const incoming = this._getOrCreateEdgeEntry(node.id).incoming;

      for (const predicate of PREDICATES) {
        const targets = node[predicate];
        if (!Array.isArray(targets)) continue;
        for (const targetId of targets) {
          if (!this.nodesById.has(targetId)) continue; // drop dangling
          const edge = { source: node.id, target: targetId, predicate };
          this.edges.push(edge);
          outgoing.push(edge);
          this._getOrCreateEdgeEntry(targetId).incoming.push(edge);
        }
      }

      this._getOrCreateEdgeEntry(node.id).outgoing = outgoing;
    }

    document.dispatchEvent(new CustomEvent("graph-loaded", { detail: this }));
  }

  /** @private */
  _getOrCreateEdgeEntry(nodeId) {
    if (!this.edgeIndex.has(nodeId)) {
      this.edgeIndex.set(nodeId, { outgoing: [], incoming: [] });
    }
    return this.edgeIndex.get(nodeId);
  }

  /** Get a single node by id. */
  getNode(id) {
    return this.nodesById.get(id) || null;
  }

  /** Get all nodes of a given type. */
  getNodesByType(type) {
    return this.nodesByType.get(type) || [];
  }

  /** Get edges for a node, split by direction. */
  getEdges(nodeId) {
    return this.edgeIndex.get(nodeId) || { outgoing: [], incoming: [] };
  }

  /** Count nodes by type. */
  getTypeCounts() {
    const counts = {};
    for (const [type, nodes] of this.nodesByType) {
      counts[type] = nodes.length;
    }
    return counts;
  }

  /** Search nodes by id or label substring (case-insensitive). */
  search(query) {
    const q = query.trim().toLowerCase();
    if (!q) return [...this.nodesById.values()];
    return [...this.nodesById.values()].filter(
      (n) => n.id.toLowerCase().includes(q) || (n.label || "").toLowerCase().includes(q)
    );
  }

  /** Total node count. */
  get nodeCount() {
    return this.nodesById.size;
  }

  /** Total edge count. */
  get edgeCount() {
    return this.edges.length;
  }

  /** Whether any data is loaded. */
  get isLoaded() {
    return this.nodesById.size > 0;
  }

  /** Get all raw attributes of a node (everything that isn't an edge predicate). */
  getRawAttributes(nodeId) {
    const node = this.nodesById.get(nodeId);
    if (!node) return {};
    const attrs = {};
    for (const [key, value] of Object.entries(node)) {
      if (!PREDICATES.includes(key)) {
        attrs[key] = value;
      }
    }
    return attrs;
  }
}

/** Singleton instance shared across the app. */
export const store = new GraphStore();
