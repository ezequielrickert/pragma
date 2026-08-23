/**
 * Shared color palette and predicate vocabulary for the Ladybug graph.
 *
 * Single source of truth — matches `dashboard/graph_assets.py`'s own
 * FAMILY_COLORS and PREDICATES exactly so the debugging tool's colors
 * are visually consistent with the static dashboard's graph card.
 */

/** One color per node type — populated types get distinct hues,
 *  reserved types (not yet emitted by any generator) share a neutral gray. */
export const FAMILY_COLORS = {
  Pantalla:   "#5b8cff",
  Componente: "#4ade80",
  Endpoint:   "#fb923c",
  Token:      "#f472b6",
  Modulo:     "#a78bfa",
  Entidad:    "#fbbf24",
  Requisito:  "#22d3ee",
  Escenario:  "#6b7280",
  Hallazgo:   "#6b7280",
  Flujo:      "#6b7280",
  Estado:     "#6b7280",
};

/** Types present in the schema but not yet populated by any generator. */
export const RESERVED_TYPES = new Set(["Escenario", "Hallazgo", "Flujo", "Estado"]);

/** All node types in display order. */
export const NODE_TYPES = [
  "Pantalla", "Componente", "Endpoint", "Token", "Modulo",
  "Entidad", "Requisito", "Escenario", "Hallazgo", "Flujo", "Estado",
];

/** Edge predicate keys — the property names on each node in export.json. */
export const PREDICATES = [
  "contiene", "navega_a", "dispara", "consume",
  "usa_token", "depende_de", "implementa", "cubre",
  "viola", "deriva_de",
];

/** Human-readable labels for each predicate. */
export const PREDICATE_LABELS = {
  contiene:    "contains",
  navega_a:    "navigates to",
  dispara:     "triggers",
  consume:     "calls",
  usa_token:   "uses token",
  depende_de:  "depends on",
  implementa:  "implements",
  cubre:       "covers",
  viola:       "violates",
  deriva_de:   "derives from",
};

/**
 * Get a color with optional alpha for backgrounds.
 * @param {string} type - Node type
 * @param {number} [alpha=1] - Opacity (0–1)
 * @returns {string} CSS color value
 */
export function colorForType(type, alpha = 1) {
  const hex = FAMILY_COLORS[type] || "#6b7280";
  if (alpha >= 1) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Render a colored type badge as an HTML string.
 * @param {string} type - Node type
 * @returns {string} HTML for the badge
 */
export function typeBadgeHtml(type) {
  return `<span class="type-badge" style="background:${colorForType(type, 0.15)};color:${FAMILY_COLORS[type] || "#6b7280"}">${type}</span>`;
}
