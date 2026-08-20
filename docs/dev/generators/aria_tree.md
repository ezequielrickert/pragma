# `generators/aria_tree.py`

## module

`tree.aria.yaml` + `tree.axtree.json`, per docs/adr/0003 - replaces the
hand-written `component_tree.py` entirely, not just its serialization.
Every screen's real Playwright `ariaSnapshot()` (role + accessible name,
the same computation a screen reader does) is captured once per page
during the crawl (`spiders/content/accessibility_snapshot.py`,
`database/ladybug/accessibility_snapshot.py`); this module is pure
post-processing over what was captured - parsing, `SCR-<hash>`/
`template_hash` computation, and `x-axtree-ref` correlation, none of
which need a live page.

## _parse_label

Playwright's ariaSnapshot() label shape: `role "name" [attr=val ...]` or
just `role` when there is no accessible name. Bracket attributes
(`level`, `checked`, ...) are dropped - ADR-0003 asks this document for
role, name, and hierarchy, not the full attribute set.

## _walk_aria_yaml

Playwright's ariaSnapshot() YAML, parsed by PyYAML, comes back as a
recursive list where each element is either a bare string (a leaf) or a
single-key `{label: [children]}` mapping (a node with children) - this
walks that shape into `{role, name, children}` nodes, the structure every
other function in this module operates on.

## _structural_shape

Role and hierarchy only, name stripped - the input `template_hash`
hashes (ADR-0003's duplicate/template detection: "40 near-identical
screens, 1 template," gotten for free as post-processing over the
snapshot already built, no new crawler instrumentation).

## _template_hash

`short_hash` (ADR-0015's pinned algorithm) over `_structural_shape`'s
canonical JSON. Two screens with identical role/hierarchy structure and
different text collapse to the same `template_hash`, regardless of what
the accessible names say.

## _axtree_preorder_node_indices

This screen's AXTree, walked via `childIds` - not array order, which CDP
does not contractually guarantee - starting one level *below* each root.
`getFullAXTree` includes the page's own RootWebArea entry, but
`page.locator("body").aria_snapshot()` enumerates body's children, not
body itself, so the walk skips exactly that one wrapper to keep both
traversals describing the same starting set of nodes.

**Unverified against a live browser** (no Playwright/CDP session
available while this was written) - the assumption that
`ariaSnapshot()`'s own YAML nesting order matches this AXTree walk's
order is reasonable (both describe the identical accessibility tree,
captured back-to-back in the same discovery pass) but not empirically
confirmed here. `_attach_axtree_refs` degrades gracefully if the two
disagree in practice.

## _attach_axtree_refs

Tags every ARIA node with its `x-axtree-ref` by walking the parsed tree
in the same pre-order the AXTree indices were produced in, one index per
node - never by matching role/name, which a page with duplicate siblings
(two identical buttons) would attribute to the wrong one. A node left
unmatched (the two trees disagreed on shape, or one ran out first)
simply carries no ref, per ADR-0003's own "reserved rather than invented"
discipline, applied here to a correlation failure instead of a missing
field.

## _build_screen

One page's captured snapshot into its `tree.aria.yaml` entry and its
`tree.axtree.json` entry - a pair, since every `x-axtree-ref` in the
first points into the second. `screen_id` is `SCR-<hash>` of the page's
own url, which is already the route-shaped canonical key every stored
`Page` carries (docs/adr/0003's screen-ID scheme: deterministic across
runs because it's derived from identity, not assigned by generation
order).

## build_aria_tree

`(tree.aria.yaml's list, tree.axtree.json's dict)` for every page with a
captured snapshot, in url order - a page discovered before this
instrumentation existed, or whose capture failed, contributes neither.

## AriaTreeDocument

`DocumentGenerator` adapter, registered under the same `"tree"` name
`component_tree.py` used - a full replacement, not an addition, per
ADR-0003. Two `kind="source"` outputs, both schema-validated
(`schemas/tree.aria.schema.json`, `schemas/tree.axtree.schema.json`)
before being written.
