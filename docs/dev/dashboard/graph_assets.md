# `dashboard/graph_assets.py`

## module

Static client-side assets for the Graph card (`dashboard/graph_renderer.py`,
ticket #163, map #159) - the CSS, the Cytoscape.js interaction logic, and
ADR-0002's node-type vocabulary. Split out of `graph_renderer.py` itself
once it crossed file-size-audit's WATCH threshold - a real SRP seam, not
just a line-count trim: this is data (what the page looks like and how
it behaves client-side), a different reason to change than
`graph_renderer.py`'s own job of assembling the page around it.

**The design is the prototype's, not this ticket's own invention.**
`docs/prototype-graph-card/` (throwaway `prototype/graph-card` branch,
ticket #162) built and reacted to five structurally different layouts
against real crawl data; `SCRIPT` ships the winner ("Variant E") largely
unchanged: the page opens collapsed to the "structural" families
(`Pantalla`, `Modulo`) rather than every node at once - ticket #162's own
finding was that all-nodes-at-once gets unreadable past a few dozen.
Clicking a node offers **View details** (a slide-over with a parameter
grid and connections grouped by `export.json`'s real predicate
vocabulary) or **Expand children** (reveals that node's direct neighbors
on the same canvas); **Show all** covers "I want to see everything."

`FAMILY_COLORS`/`RESERVED_TYPES` carry ADR-0002's full node vocabulary -
populated types get a real color, reserved types (schema-listed, not yet
emitted by any generator) render dimmed in the legend rather than being
silently absent, confirmed readable in ticket #162's own prototype.
`SCRIPT` carries two placeholders, `__FAMILY_COLORS__`/`__RESERVED_TYPES__`,
substituted with real JSON by `graph_renderer.render_graph_page`.

**`?family=<Type>` (ticket #176, map #172).** `initialVisibleIds` reads
this URL param on load - the landing page's own KPI tiles
(`dashboard/kpi_section.py`) link here pre-filtered to their own real
node family. Falls back to the ordinary structural-families default
whenever the param is absent, names an unknown type, or names a family
with zero real nodes this run - a linked-through-but-empty view would be
a worse landing than the familiar default.

**Canvas/detail-view mechanics, ticket #174 (map #172).** `COSE_LAYOUT` is
one shared constant (was four separately-tunable copies) with
`nodeRepulsion: 400000` - cose's own real default; this file previously set
`9000` (44x weaker), the actual cause of nodes rendering stacked on a real
crawl's denser hub cluster. `truncateLabel` caps a node's on-canvas label at
`LABEL_MAX_LENGTH` - the full label always still shows untruncated once a
node is clicked (the detail drawer never truncates). The drawer is
`max(500px, 50vw)` instead of a fixed 360px, and its own ego-graph is taller
(340px, was 180px) with pan/zoom actually enabled (previously forced off).
`openDetail` opens the drawer *before* rendering the ego-graph into it -
cytoscape reads its container's real dimensions at construction time, and
resizes/fits again once the drawer's own CSS width transition genuinely
finishes (a `transitionend` listener, not a fixed delay) rather than
whatever size a still-animating container happened to have.
