# database/ladybug/options.py

## module

`Option` and `HAS_OPTION` - the last JSON blob (`components.options`) retired
into real nodes.

`record_component_options` receives one of three shapes, told apart by which
fields are present:

- **stepper** (`increment_path`/`decrement_path`): not a list of choices at all,
  but a compound control - a container, a plus, a minus and a current value.
  Encoded into option rows under the reserved `group_name` `"stepper"`, with
  the value carried as a `value:`-prefixed text row.
- **choice_group**: real DOM choices, each with its own selector, folded into
  one representative component by consolidation. `path` on each row is the
  member's original selector from before that folding.
- **revealed_options**: choices that appeared only after a click and have no
  stable selector of their own, so their rows carry no `path`.

**The detection is mirrored on both sides rather than shared**, and that is
deliberate: the write side works from live discovery dicts, the read side
(`component_classifier.describe_options_from_rows`) from a graph query result,
and forcing both through one JSON-shaped intermediate is exactly the blob this
step deleted.

## _ladybugoptionsmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## _option_rows_and_group

`(rows, group_name)` for whichever of the three shapes arrived, or `None` for
anything unrecognized - the same defensive fallback `describe_options` uses on
the read side. Returning `None` rather than raising keeps one odd control from
failing a whole discovery pass's write.

## record_component_options

Replaces one component's entire option set. A full rebuild rather than a merge,
because a stepper's `current_value` and a revealed dropdown's member set both
change between rediscovery passes and **neither has a stable per-option key to
merge on** - there is nothing to `MERGE` against, so a merge would accumulate
stale choices.

`option_labels` is accepted and **not stored**. It is the pre-rendered display
string `GraphStoreSink` computes via `format_option_choices`, and every caller
that wants it recomputes it from the real `Option` rows when it needs it -
storing a second copy would be a denormalization that can go stale against the
rows beside it. The parameter stays for interface parity with the callers that
still pass it.

That non-storage is also the direct cause of the D5 regression documented at
`docs/dev/generators/component_catalog.md#_with_option_labels`: the catalogue
kept reading the flat key this method stopped keeping, and lost every
dropdown's options without erroring.
