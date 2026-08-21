# database/ladybug/container_forest.py

## module

Whole-site composite-tree read for `LadybugGraphStore` - what
`analysis/composite_matching.py`'s matching pass (issue #139) needs
before it can bucket or score anything.

## _ladybugcontainerforestmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## get_container_forest

`{page_url: [root_dict, ...]}` - every page's top-level composites, each
a nested tree whose `children` mix leaf component dicts and nested
composite dicts recursively shaped the same way as the root. A composite
is a page's *root* if no other composite on that same page `CONTAINS` it
- judged per page, not globally, since a shared `Container` can
legitimately be a root on one page and a nested child on another. Read as
four whole-site queries, not one root at a time recursed via `CONTAINS*`.

## _build_composite_tree

One composite's tree, recursively. Guards against a cycle a genuine DOM
tree can never produce but a canonical, shared `Container` reused in an
unexpected shape could in principle.
