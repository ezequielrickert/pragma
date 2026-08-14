# `spiders/orchestration/graph_sink/component_facts.py`

## module

Pure mapping helpers - no I/O, no `GraphStore` dependency, same "pure
function, no side effects" placement as `component_classifier.py`'s own
functions. Split out of `graph_sink.py` since these two functions have a
different reason to change (the JS-discovered-component-dict -> stored-
field mapping) than `GraphStoreSink`'s own reason (how/when each fact
gets written).

## option_labels_for

`format_option_choices(describe_options(options_json))` in one call -
the clean, human-readable projection of one `options` JSON blob (e.g.
`["Mi Gusto (selected)", "Solo Empanadas", ...]`), computed at write
time and stored as `option_labels` alongside the raw JSON on the same
`Component` node. Called from all three `record_component_options`
sites (`GraphStoreSink.record_inventory`'s stepper write,
`_record_choice_group`, `record_revealed_options`) so every options
write gets this second, clean field for free, without needing external
tooling (`component_tree.py`'s rendered `.md`) just to read a choice
list back.

## component_facts

Pure mapping from one raw, JS-discovered component dict
(`discover_components.js`'s per-element shape - `attributes`/`style`
nested dicts, plus top-level `placeholder`/`label`/`name`/`disabled`/
`required`/`form`) onto `GraphStore`'s `ComponentFacts`
(`docs/dev/core/interfaces.md#ComponentFacts`). Kept as a standalone
function rather than inlined into `GraphStoreSink._component_args` so
the attribute/style field-name mapping - the part actually at risk of a
left-side/right-side typo - has its own direct unit test
(`tests/test_graph_sink_component_facts.py`) that doesn't need a real
browser round-trip to exercise.
