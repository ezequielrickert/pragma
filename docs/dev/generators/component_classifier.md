# `src/generators/component_classifier.py`

## module

Deterministic component classification and grouping - the "what is
this, what does it offer, what state is it in" facts an LLM narration
pass (see `SimplePRDGenerator._write_component_catalog`) turns into
readable documentation.

Every function here is pure and DOM-attribute-driven, no model call
involved - matches this project's established preference (see
wiki/local-and-small-model-constraints.md) for deterministic, code-side
signals over model judgment wherever the underlying facts are already
mechanically knowable. A small/weak local model narrates these facts
into prose; it never has to *notice* them itself.

## classify_component_type

A short, human-readable type label from tag/role/input_type alone - no
LLM call, no page context needed. This is the label the component
catalog's narration prompt is built around; the model is told what kind
of thing it's describing rather than asked to guess from raw HTML.

## find_revealed_options

Components with an "option"-family role that a trigger's click/fill
just made available - either genuinely new to the DOM (matched by CSS
path not present in `before` at all - a React/Radix-portal widget that
mounts its popover content on open), OR already present in `before` but
CSS-hidden (`visible: False`) and now `visible: True` in `after` - the
other common pattern (a plain `hidden`/`display:none` toggle, the same
"present in the DOM the whole time, just hidden until a trigger" shape
`PlaywrightScraper._discover_components`'s own mega-menu handling
already assumes elsewhere). Both are "the user can now see and act on
this that they couldn't a moment ago" - the property this function
actually exists to detect - so both count as revealed.

A component with no `visible` key at all in either snapshot (a caller
that doesn't track it) is never treated as newly-revealed via the
became-visible path - only the by-path-absence check applies for it -
preserving this function's original behavior for such callers.

Called from `PageVisitor.visit` comparing a page's component list
immediately before vs. after a same-page interaction - this is the
concrete "clicking 'Tercera Docena' revealed a 9-item bakery picker"
case: the trigger itself doesn't carry its own options in a single DOM
snapshot, they only exist once it's been opened, so this has to be a
before/after diff, not a single-snapshot classification like the other
functions here.

## group_steppers

Detect increment/decrement button pairs sharing a common parent
container (a quantity stepper: "-" / count / "+") and, if present, the
numeric-looking sibling between them.

Grouping key is the shared *parent* CSS path, not any single
component's own identity - a stepper's "+"/"-" buttons are siblings
under one container, and grouping by that container is what ties them
together as one logical control rather than three unrelated
buttons/text. Returns one entry per detected stepper; a page with no
such pattern returns an empty list, cheaply.

## group_choice_sets

Radio/checkbox components sharing the same `name` attribute - the
standard HTML pattern for "these inputs are one logical choice, not
independent fields" (a single radio input alone isn't meaningfully
describable without its siblings; a whole named group is what a human
would call "one control").

Groups of size 1 are dropped - nothing to group without at least one
sibling sharing the same `name`.

## describe_options

Parse a Component's raw `options` JSON blob (`GraphStore`'s
`record_component_options` field) and classify which of the three known
shapes it is, returning a normalized `{"kind", ...}` dict, or `None` if
empty/unparseable/unrecognized. The single place every consumer of this
field (`graph_prd_synthesizer.py`'s catalog narration,
`component_tree.py`'s deterministic renderer) goes to interpret it, so
the three-shape disambiguation logic exists exactly once:

- `{"kind": "stepper", "container", "increment_path", "decrement_path",
  "value_path", "current_value"}` - `group_steppers`' output, written by
  `GraphStoreSink.record_inventory`.
- `{"kind": "choice_group", "group", "choices": [{"text", "selected"}]}`
  - `group_choice_sets`' output, same writer.
- `{"kind": "revealed_options", "trigger", "choices": [{"text",
  "selected"}]}` - `find_revealed_options`' output, written by
  `GraphStoreSink.record_revealed_options` (Phase 1).
