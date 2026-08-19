# database/ladybug/containment.py

## module

The `Container`/`CONTAINS` tier: which layout and landmark elements wrap
which components, written from `discover_components.js::structuralAncestorsOf`
and read back as "which region is this component in".

**Direct edges only, no transitive closure.** The retired DuckDB backend
stored one row per `(component, ancestor)` pair at every depth - 58,714 rows
in the snapshot that shaped the storage plan, 2.1 per component. Here each
container points only at the thing one step nearer the leaf, and any deeper
question is a `CONTAINS*` traversal. That is what makes storing only the
direct edges correct rather than lossy.

**Containers are per page, not shared.** A container's id is
`component_id(page_url, path)`, so `<main>` on two pages is two nodes. There
is no `Page`-to-`Container` edge in the schema, which is why the read below
reaches containers *through* their components rather than from the page.

## _ladybugcontainmentmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`, same contract as
every other mixin here.

## record_component_ancestors

`entries` is one `{"path", "ancestors"}` per component with `ancestors`
ordered nearest-first - exactly what `GraphStoreSink.record_inventory`
assembles after its own `record_components` batch.

Two deliberate choices that look like belt-and-braces and are not:

- The leaf edge `MERGE`s the `Component` rather than `MATCH`ing it.
  Confirmed against the real engine: a `MATCH` that matches nothing drops
  the *entire* pattern silently, not just that clause, so a batch arriving
  before the component row existed would lose every containment edge with no
  error at all.
- The stub sets `path` in its `ON CREATE`, not only `id` - the ghost-node
  mistake `options.py`'s stub also avoids. A component that only ever gets
  this stub would otherwise report an empty `path` forever.

Consecutive pairs of the nearest-first chain are exactly the direct edges,
which is the whole reason the JS contract specifies that order.

## get_component_regions

Answers the one question D5 and D2 actually ask of containment: not the full
ancestor chain, but the single region a reader would name.

**Nearest landmark wins.** A `<form>` inside `<main>` reports `main`; a
search box inside a `<nav>` that is itself inside `<main>` reports
`navigation`, because the inner region is the informative one.

Nearest is resolved with `length()` on the recursive relationship.
Confirmed against the real engine: `size()` rejects a `RECURSIVE_REL`
outright (*"Function SIZE did not receive correct arguments: Actual:
(RECURSIVE_REL)"*), and `length()` is the one that accepts it. With
`ORDER BY` on that length, the first row per component is already the
nearest, so there is no second query and no per-component walk.

**A component in no landmark is absent, not present with `""`.** A caller
asking "which region is this in" gets the same answer from a missing key as
from an empty string, and a missing key cannot be misread as a region
genuinely named `""`. `{}` for a site with no recorded ancestry, which is
also how a crawl from before containment capture reads back - the documents
say so rather than rendering "no regions" as if it were a finding.

## get_page_landmarks

`{page_url: {landmark: count}}` - how many distinct landmark regions of each
kind a page has.

The question `get_component_regions` cannot answer. That one reports the region a
*component* sits in, so a page with two separate `<header>`s looks identical to a
page with one. Landmark structure is a property of the page, and
`generators/accessibility.py` needs it that way to report a missing `main` or a
duplicated `banner`.

`count(DISTINCT region.id)`, not `count(region.id)` - confirmed against the real
engine that the difference bites here: two banners holding three components
between them count 3 naively and 2 distinctly, and 2 is the number WCAG cares
about.

Reached through components, because there is no `Page`-to-`Container` edge in the
schema. A landmark holding no discovered component is invisible here - a floor on
what this can report rather than a bug, since an empty region has nothing to be
inaccessible about.
