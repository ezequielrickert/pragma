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
