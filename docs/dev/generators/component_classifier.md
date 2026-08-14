# `generators/component_classifier.py`

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

## group_option_families

Option/menu-item components (`role` in `option`, `menuitem`,
`menuitemcheckbox`, `menuitemradio`) sharing an immediate parent CSS
path - the DOM shape of one dropdown or menu's list of choices (a
Radix/react-select-style popover's `role="option"` children, a
`role="menu"`'s `role="menuitem"` children). Same grouping-by-shared-
parent idea as `group_steppers`, but for an arbitrary-length list
instead of a fixed increment/decrement/value triple.

Deliberately excludes `role="tab"` even though it shares option-family
markup elsewhere in this module (`_OPTION_ROLES`, used by
`find_revealed_options`): a tab usually gates materially different page
content, so collapsing a page's tabs into one storage node the way a
dropdown's choices collapse would lose real per-tab tracking. See
`_LIST_MEMBER_ROLES`.

Groups of size 1 are dropped, same reasoning as `group_choice_sets` - a
lone `role="option"` with no siblings isn't "a list" worth
consolidating; it gets `record_component`'s ordinary per-element path.

Written by `GraphStoreSink.record_inventory` to collapse what used to be
one Neo4j `Component` node per discovered option into a single
representative node per list (see graph_sink.md#_record_choice_group) -
a dropdown with 5 choices no longer produces 5 near-identical nodes
differing only by which choice they are.

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
- `{"kind": "choice_group", "group", "choices": [{"path", "text",
  "selected"}]}` - `group_choice_sets`/`group_option_families`' output,
  same writer. `path` (added alongside `group_option_families`) is each
  choice's own original CSS path - since consolidation means most
  choices no longer have their own Component node, this is the only
  place their identity survives, used to attribute a specific choice's
  later interaction back to its label (see
  `component_tree.md#_build_option_redirects`).
- `{"kind": "revealed_options", "trigger", "choices": [{"text",
  "selected"}]}` - `find_revealed_options`' output, written by
  `GraphStoreSink.record_revealed_options` (Phase 1). No per-choice
  `path`: `find_revealed_options` only ever diffs text/selected, it was
  never given one to carry.

## format_option_choices

Renders `describe_options`' normalized shape as short, human-readable
display strings - e.g. `["Mi Gusto (selected)", "Solo Empanadas", ...]`
for a `choice_group`, `["stepper (current value: 3)"]` for a stepper.
Promoted here from `component_tree.py` (where it was originally a
private `_format_variants`, used only for that module's rendered
`variants=[...]` tree line) so `graph_sink.py` can call the exact same
formatting logic to compute `option_labels` - the clean projection of a
Component's raw `options` JSON stored directly on the graph node (see
`docs/dev/spiders/graph_sink.md#_option_labels_for`), instead of that
clean form only ever existing inside a generated `.md` file. Both
callers now share one implementation; there is no `component_tree.py`
copy left to drift out of sync with it.

## choice_text_by_path

The `path -> text` lookup both `component_tree.py`'s
`_build_option_redirects` and `graph_prd_synthesizer.py`'s
`_choices_leading_elsewhere` need, factored out here rather than each
rebuilding the same dict comprehension over a `choice_group`'s choices -
this module already owns every other piece of `options`-shape
interpretation (`describe_options` above), so the one place a
`source_path` gets resolved back to a label belongs here too.
