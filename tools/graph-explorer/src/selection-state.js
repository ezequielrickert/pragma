/**
 * SelectionState — shared selection and navigation history.
 *
 * Persists to sessionStorage so the selected node survives switching
 * between the Graph and Lists pages. Emits "selection-changed"
 * CustomEvents on `document` for any component to listen to.
 */

const STORAGE_KEY = "pragma-graph-explorer-selection";
const HISTORY_KEY = "pragma-graph-explorer-history";
const MAX_HISTORY = 50;

class SelectionState {
  constructor() {
    this._selectedNodeId = sessionStorage.getItem(STORAGE_KEY) || null;
    this._history = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]");
  }

  /** Currently selected node id, or null. */
  get selectedNodeId() {
    return this._selectedNodeId;
  }

  /** Navigation history stack (most recent last). */
  get history() {
    return [...this._history];
  }

  /**
   * Select a node — pushes the previous selection onto the history stack.
   * @param {string} nodeId
   */
  select(nodeId) {
    if (nodeId === this._selectedNodeId) return;

    // Push current selection to history before changing
    if (this._selectedNodeId) {
      this._history.push(this._selectedNodeId);
      if (this._history.length > MAX_HISTORY) {
        this._history = this._history.slice(-MAX_HISTORY);
      }
    }

    this._selectedNodeId = nodeId;
    this._persist();
    document.dispatchEvent(
      new CustomEvent("selection-changed", { detail: { nodeId, source: "select" } })
    );
  }

  /**
   * Navigate back to the previous node in history.
   * @returns {string|null} The node id navigated back to, or null if empty.
   */
  goBack() {
    if (this._history.length === 0) return null;
    const previousId = this._history.pop();
    this._selectedNodeId = previousId;
    this._persist();
    document.dispatchEvent(
      new CustomEvent("selection-changed", { detail: { nodeId: previousId, source: "back" } })
    );
    return previousId;
  }

  /** Clear selection and history. */
  clear() {
    this._selectedNodeId = null;
    this._history = [];
    this._persist();
    document.dispatchEvent(
      new CustomEvent("selection-changed", { detail: { nodeId: null, source: "clear" } })
    );
  }

  /** @private */
  _persist() {
    if (this._selectedNodeId) {
      sessionStorage.setItem(STORAGE_KEY, this._selectedNodeId);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
    sessionStorage.setItem(HISTORY_KEY, JSON.stringify(this._history));
  }
}

/** Singleton shared across the app. */
export const selectionState = new SelectionState();
