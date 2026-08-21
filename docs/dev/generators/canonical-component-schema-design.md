# Canonical component/composite graph schema

Resolves [Decide canonical component/composite graph schema](https://github.com/ezequielrickert/pragma/issues/134),
child of [Component matching: embedding-based dedup and family grouping](https://github.com/ezequielrickert/pragma/issues/127).

Reads against the live DDL in `database/ladybug/schema.py`.

## Core principle: collapse is a literal row merge, not a pointer layer

When two component instances match at the exact tier, they stop being two rows. The N page-
scoped `Component`/`Container` rows a navbar link used to produce become **one** row, and every
edge that used to point at any of the N originals gets repointed at that one row. There is no new
`CanonicalComponent` wrapper node sitting above the originals — `Component` and `Container`
themselves *are* the canonical thing once collapsed. A pointer-layer design would still store the
navbar N times underneath an indirection; that doesn't remove the repetition, it just hides it a
layer down.

## What moves off the node, onto the edge

`Component.id` and `Container.id` currently embed `page_url` (`"{page_url}|{path}"`). Dropping
that means the row is no longer inherently tied to one page — which is the whole point — but a
few fields on both tables were only ever true of one page's rendering of the thing, not of its
identity:

| Field | Was on the node | Now on |
|---|---|---|
| `path` (CSS selector) | `Component`/`Container` | edge property |
| `x`, `y`, `width`, `height` | `Component` | edge property |
| `element_id` | `Component` (a `ComponentFacts` column) | edge property |

The test for "moves to the edge" is simple: does #131's exact-tier vector treat this field as
part of identity? If yes, it stays on the node (`tag`, `role`, `css_class`, `text`, style props,
`component_type`, etc.) — and that's correct by construction, since an exact match already means
those values are identical across every instance being merged. If no (`path`, geometry,
`element_id` — all excluded or only loosely weighted in #131 for exactly this reason), it's
page-instance data and belongs on the edge connecting a `Page` to the canonical node, not on the
node itself.

```
CREATE REL TABLE IF NOT EXISTS HAS_COMPONENT(
    FROM Page TO Component,
    path STRING DEFAULT '',
    element_id STRING DEFAULT '',
    x DOUBLE, y DOUBLE, width DOUBLE, height DOUBLE);
```

`HAS_COMPONENT` already exists (`FROM Page TO Component`, no properties today) — this adds the
edge properties above; no new edge table for the component case.

## `HAS_CONTAINER`: a gap that exists independent of collapse

Today there is **no edge from `Page` to `Container` at all** — a `Container` is only reachable by
walking `CONTAINS` from another `Container`/`Component`, so there's no way to query "which
composites are on this page" directly. #132's matching needs exactly that (enumerate per-page
`Container` roots to bucket before any pairwise work), so this is needed regardless of whether
collapse or family-grouping ends up firing for any given composite:

```
CREATE REL TABLE IF NOT EXISTS HAS_CONTAINER(
    FROM Page TO Container,
    path STRING DEFAULT '',
    element_id STRING DEFAULT '');
```

`Container.css_class` stays on the node (it's the root's own identity signal, per #132's step 2
— the root gets its own leaf-style vector the same way a `Component` does), not moved to the
edge.

## `Interaction`'s page linkage breaks, and needs an explicit fix

`Interaction` currently has no direct edge to the page it happened on — `PERFORMED(Component →
Interaction)` implied it, because the performing `Component`'s id embedded `page_url`. Once
`Component` is canonical and page-decoupled, that implication is gone. Fix:

```
CREATE REL TABLE IF NOT EXISTS OCCURRED_ON(FROM Interaction TO Page);
```

Additive — `PERFORMED` and `RESULTED_IN` (the interaction's navigation *destination*, a different
fact) keep their current meaning unchanged. `Interaction.source_path` continues to carry the
specific selector that particular interaction used, same as today.

## Family tier: a parallel `CompositeFamily`, not a repurposed `ComponentFamily`

`ComponentFamily` (`tag`, `component_type`, `common_classes`, `purpose`) is shaped for a single
`Component`; a `Container` subtree doesn't fit those columns. Rather than stretching
`ComponentFamily` to cover both, a composite gets its own family node, minimal by design:

```
CREATE NODE TABLE IF NOT EXISTS CompositeFamily(
    id SERIAL PRIMARY KEY,
    root_tag STRING DEFAULT '',
    purpose STRING DEFAULT '');

CREATE REL TABLE IF NOT EXISTS COMPOSITE_VARIANT_OF(FROM Container TO CompositeFamily);
```

Plus its own `DERIVED_FROM` entry (`FROM CompositeFamily TO Container`), mirroring
`ComponentFamily`'s existing one. This coexists with `ComponentFamily`/`VARIANT_OF` rather than
replacing or extending it — leaf-level family grouping and composite-level family grouping are
answering different questions at different granularities, and keeping them as separate node
types keeps each one simple instead of one node table trying to serve two shapes.

`ComponentFamily.common_classes` (built for the old Jaccard-on-`css_class` clustering) isn't
touched by this ticket — it stops being what determines family membership once #131's vector
replaces Jaccard, but it's still a reasonable descriptive summary for
`component_family_narrator`'s narration, so no schema change is needed there, just a semantics
note for whoever implements the switch-over.

## Summary of DDL changes

- `Component.id` / `Container.id`: drop `page_url` from the primary key (content-derived
  identity instead — the exact scheme is #131/#132's leaf/composite vectors, not a new decision
  here).
- `Component`: drop `path`, `x`, `y`, `width`, `height`, and the `element_id` `ComponentFacts`
  column (moved to `HAS_COMPONENT`).
- `Container`: drop `path` and `element_id` (moved to `HAS_CONTAINER`).
- `HAS_COMPONENT`: gains `path`, `element_id`, `x`, `y`, `width`, `height` properties.
- New: `HAS_CONTAINER(Page → Container, path, element_id)`.
- New: `OCCURRED_ON(Interaction → Page)`.
- New: `CompositeFamily` node + `COMPOSITE_VARIANT_OF(Container → CompositeFamily)` edge +
  matching `DERIVED_FROM` entry.

## What this hands off

Where this schema migration actually runs in the static→cluster→dynamic pipeline, and how the
dynamic engine uses a collapsed canonical component's `HAS_COMPONENT`/`HAS_CONTAINER` edges to
interact once per canonical node instead of once per page instance:
[Decide pipeline placement and dynamic-engine interact-once behavior](https://github.com/ezequielrickert/pragma/issues/135).
