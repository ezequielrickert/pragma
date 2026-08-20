# `generators/component_catalog.py`

## module

D5: what the site is built from, per component, with props and variants.

**Why this is not the Atomic Design pyramid.** The plan
(`research/plan-generacion-de-documentos.md`, Fase 3) originally proposed
deriving atoms, molecules, organisms and templates from CSS-path prefixes.
Two things killed that:

- The graph does not contain the containers. Discovery records interactive
  elements and text leaves; the `<div>`, `<nav>` and `<section>` that
  *are* the molecules and organisms are never nodes. What a prefix gives
  you is a shared string, not an element - so you cannot tell a `<nav>`
  from an anonymous layout `<div>`, and the tag is the strongest signal
  there is for what an organism is.
- The pyramid feeds nothing. Someone rebuilding this UI needs a
  component's props and variants; the level it sits at is a label.

So the level is reported only where the captured data actually settles it,
and omitted otherwise. Organisms and templates stay out of scope until the
nearest landmark ancestor is captured too - one line in
`discover_components.js`, with an exact precedent in the same file
(`form: el.closest('form')`), but not worth doing before the catalogue
exists and shows what is missing.

**No new capture, no model call.** Families already exist, and every prop
below is a `ComponentFacts` field the crawl has been persisting all along.

## _prop_fields

The fields that describe a component's *interface*. Style and geometry
(`color`, `background_color`, `font_size`, `rect`) are deliberately
absent: they belong to the design-token document, D10. The one exception
is `background_color`, read in `_variants` - not as a prop, but as the
thing that tells two variants apart.

## CatalogProp

`varies` is what makes this useful. A field every instance shares and a
field each instance sets differently look identical in the data, and the
difference is exactly "fixed trait" versus "prop you must pass": a
`required` that is `true` on all twelve inputs is part of the component,
while a `placeholder` that differs on all twelve is an argument.

## CatalogVariant

Keyed by modifier classes *and* background colour, because a design system
can express the same distinction either way - a `btn-danger` class or a
hardcoded red. Grouping on only one of them merges variants that a reader
can plainly see are different.

## CatalogEntry

## regions

The landmark regions a pattern's instances actually sit in. A button used in
both the navigation and the footer is a different component from one used
only in the footer, and that belongs next to its props.

Empty means one of two things - no instance is inside a landmark, or the
crawl predates containment capture - and the two are indistinguishable here.
`ComponentCatalogDocument.generate` says which possibilities are open rather
than letting a blank line imply "no regions" as a finding.

## _regions_of

Reads each member's region out of `get_component_regions()`'s
`{page_url: {path: landmark}}` and returns the distinct set, sorted. A
member in no region contributes nothing rather than an empty string.

## catalog_for

## component_name

A single-word parenthetical is kept, a longer one dropped.

`text field (email)` and `text field (password)` are genuinely different
components and must not collide, so `email` stays. `combobox (searchable
dropdown)` and `custom control (component-library element, no native
tag/role)` are one component with a prose gloss; keeping those produces
identifiers nobody would type.

## _atomic_level

Two things in the captured data speak to composition: an indivisible HTML
tag, and `facts.form` (discovery already records `el.closest('form')`).
Everything else would be a guess, and the field is omitted instead - an
empty level is readable as "not determined", while a wrong one is read as
fact.

## _variants

`common_classes` already holds what the whole family shares, so whatever
remains on an individual member **is** the modifier. That is what turns a
primary/secondary pair into two variants of one component instead of two
separate components - and it comes free from the clustering that already
happened.

## _with_option_labels

`option_labels` is the one entry in `_prop_fields` that is not a ledger
key. The ledger carries a choice-group's options as `options` - the
`(rows, group_name)` pair the `Option` table reads back as - and this
derives the display strings from it with the same two helpers
`component_tree.py` and `graph_prd_synthesizer.py` use
(`describe_options_from_rows` then `format_option_choices`).

It used to be a stored field: `graph_sink` pre-rendered the labels and
wrote them next to a JSON `options` blob. When the `Option` table replaced
that blob, `component_tree.py` and `graph_prd_synthesizer.py` moved to
reading `options`; this document did not, and kept asking for a key that
no longer arrives. Every dropdown, `select` and consolidated choice-group
in the catalogue lost its options, silently - a prop absent because the
data is missing renders exactly like a prop absent because the component
has none. `tests/test_component_catalog.py`'s own fixture supplied
`option_labels` directly, so no test exercised the real ledger shape.

Derived into a copy (`{**member, ...}`), never assigned onto the ledger
entry: `flat_component_ledger` hands out the same dicts to every generator
in the run, and a document that edits its own input is a document that
changes the one after it.

## catalog_for

The three store reads `generators/custom_elements.py::build_custom_elements_document`
needs, in one place - `ComponentCatalogDocument`/`ComponentCatalogData` used
to carry byte-identical copies of them before ticket #101 folded both into
one CEM document, which is exactly how the prose catalogue and the JSON
catalogue could drift into describing different things.

## build_catalog

## member_count

Counted from the members actually resolved against the ledger, not from
`family.member_paths`.

A family node can name a component the ledger no longer holds - families
are rebuilt from scratch each run, and a `fresh: false` graph can carry
stale membership. Reporting "3 instances" while describing two, with a
variant table that sums to two, is the kind of quiet inconsistency that
makes a reader stop trusting every other number in the document. `used_on`
is derived the same way and for the same reason.
