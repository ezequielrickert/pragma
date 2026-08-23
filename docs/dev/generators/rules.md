# generators/rules.py

## module

Rule derivation - one `SemanticRule` per declared single-field constraint on
a form's field-bearing `Component`s, plus one `SemanticRule` per real
`<select>`'s declared option set, per 'Research Rule provenance split and
statement granularity' (issue #190). `kind="declared"`, `confidence=1.0`
throughout: read straight off markup, no model call, no human review.
`kind="inferred"` is explicitly out of scope for this tier's writer so far.

Grouped through `data_model.group_form_components` - the exact
field-membership filter `build_entities` itself uses - so every Rule's
`derived_from` component already has (or, in the same run, will have) a
`Field` reachable through `EDITS`; `database/ladybug/rule.py::record_rules`
resolves each Rule's own `GOVERNS(Rule->Field)` edge through that join.

Pure and deterministic, no model call: a markup attribute is either
declared or it isn't, nothing here needs judgment.

## _declared_constraints

Every declared single-value constraint on one field, as terse `key=value`
statements (or the bare `"required"`) - mirroring
`data_model.py::_validation`'s own convention, one row here per constraint
rather than that function's single combined string. Covers `type`,
`required`, and the numeric/length/pattern attributes this ticket added
capture for: `pattern`, `min`, `max`, `minlength`, `maxlength`, `step`.

## _option_set_statement

`"one of: [a, b, c]"` for a real `<select>`'s declared option set, else
`""`. Scoped to `tag == "select"` and the `choice_group` `Option` shape - a
JS-driven combobox's revealed choices are runtime state observed by a
click, not markup this tier can call declared, and a native `<select>`'s
own `<option>` children are not discovered as separate components at all
today (`component_classifier.py::group_option_families`'s own docstring),
so most real selects yield no rows here and no Rule - honest under this
tier's "only what is captured" rule, not a bug in this derivation.

## build_rules

One `SemanticRule` per declared constraint on every form field the crawl
found, plus one per real `<select>`'s declared option set. Sorted by
`(derived_from, statement)` for reproducible output. Every field-bearing
`Component` `group_form_components` selects is walked once, so a component
with no declared constraint at all (a plain, unconstrained text field)
contributes no rows.
