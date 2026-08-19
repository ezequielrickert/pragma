# `architecture` graph-metrics derivation and module boundaries contract

**Status**: accepted

The format audit's section 3.2 specifies that architectural metrics (module boundaries, depth, bottlenecks) must not be hand-written prose but reproducible calculations over the underlying property graph. This ADR locks the derivation formulas, community detection methodology, and execution pipeline location for `architecture`, fulfilling the `Modulo` node dependencies reserved in ADR-0002.

Decided, resolving the ticket's four open points:

**1. Module Boundaries Derivation (`module_id` / `Modulo`).** Module boundaries are derived deterministically from the Kùzu graph via a two-stage hybrid pass:
1. **URL Path-Prefix Clustering**: High-confidence initial grouping based on route path segments (e.g. `/admin/*` -> `admin` module, `/checkout/*` -> `checkout` module).
2. **Leiden Community Detection**: Graph topology clustering (optimizing modularity over navigation and interaction edges) applied to unclustered nodes or dynamic SPA routes lacking path prefixes.

Populates the reserved `Modulo` nodes and `contiene` edges in `export.json` (ADR-0002).

**2. Module Depth Calculation (`depth`).** Screen and module depth is calculated as the **shortest path distance (BFS)** from the root entry screen (`SCR-root`, the initial crawl seed URL). Screen depth equals `min_distance(SCR-root, screen)`. Module depth is the minimum screen depth among its constituent screens, representing the minimal click/navigation distance required from the entry point.

**3. Bottleneck Identification.** Nodes (screens or API endpoints) are classified as architectural bottlenecks if their **betweenness centrality** on the navigation/consumption graph falls within the top 90th percentile, combined with an in-degree threshold (`in_degree >= 3`). This identifies single points of passage (e.g. authentication gateways, central navigation hubs, critical API endpoints).

**4. Execution Pipeline & Source Document.** Graph metric calculations run inside `core/graph_metrics.py` as a graph analysis pass during `architecture` generation against the live Kùzu graph. Outputs feed `architecture.calm.json` (ADR-0010) as the machine-checkable **Source Document** (Capa 2) — module boundaries become CALM `module`-kind nodes joined to their member `screen`/`component` nodes via `composed-of` relationships — and populate `export.json`'s reserved `Modulo` entities via `contiene` edges. `architecture.md` (ADR-0010, an arc42 view rendered from `architecture.calm.json` and `architecture.cyclonedx.json`) acts as the **View Document** (Capa 3).

*Amendment: this point originally named the output `architecture.json` and left the view format open ("Structurizr/C4 view"), written before ADR-0010 locked CALM + CycloneDX as two separate source documents. Updated to match; the derivation formulas in points 1–3 are unaffected.*

Wayfinder ticket: [architecture: design graph-metrics derivation from export](https://github.com/ezequielrickert/pragma/issues/72), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
