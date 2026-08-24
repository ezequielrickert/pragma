# database/ladybug/rule.py

## module

`Rule` write and read path for `LadybugGraphStore` - the semantic tier's
fourth writer, following `flow.py::record_flows`'s pattern
(full-rebuild-per-run, `DERIVED_FROM`-provenanced, no-provenance-no-write).

**Deletes are scoped by source label for `DERIVED_FROM`, same reasoning as
`screen.py`/`flow.py`.** `DERIVED_FROM` is one rel table shared by every
semantic-tier writer - a blanket delete here would erase whichever other
writer ran first on this same run. `record_rules` deletes only
`Rule`-sourced `DERIVED_FROM` edges. `GOVERNS` needs no such scoping: the
schema declares it `FROM Rule TO ...` only (`Entity`/`Field`/`Flow`/
`Endpoint` targets, `Field` the only one populated so far), so `Rule` is
its only possible source label and a blanket delete is unambiguous.

**A `Rule` has a natural key, unlike `Flow`.** Two components can each
declare `"required"`, but one component never declares the same constraint
twice - `(source Component, statement)` is unique by construction (a
control has one `min`, one `pattern`, one `required` flag, one declared
option set), so `record_rules` writes each Rule's node and `DERIVED_FROM`
edge in one statement, then re-`MATCH`es it by that pair to attach its
`GOVERNS` edge, rather than needing `flow.py`'s single do-everything
statement.

**`GOVERNS` is best-effort, not enforced.** A Rule's `derived_from`
component reaching a `Field` via `EDITS` depends on `record_entities`
having already run over the same component set this run - true whenever
`core/engine.py` calls `_apply_rules` after `_apply_data_model`, as it
does. If no such `Field` exists (a caller running this writer in
isolation, an out-of-order run), the Rule and its `DERIVED_FROM`
provenance are still written; only the `GOVERNS` edge is silently absent,
matching this schema's own stance that `GOVERNS`'s `Entity`/`Flow`/
`Endpoint` targets stay unpopulated rather than erroring.

## _ladybugrulemixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`, the same
contract every other mixin in this package has.

## record_rules

Replaces this site's `Rule` set with `rules` - a full rebuild, like
`record_screens`/`record_flows`: a Rule has no stable identity across a
rebuild that adds, removes or reshapes form fields, so patching in place
isn't sound.

Raises `ValueError` if any rule has no `derived_from` - mirrors
`record_entities`/`record_screens`/`record_flows`'s own enforcement: this
tier is only worth having if every node in it can be traced back to what
it was observed from.

## _write_rule

One `Rule` node, its `DERIVED_FROM` edge, and (best-effort) its `GOVERNS`
edge toward the `Field` its source `Component` edits. Two Cypher
statements: the first `MERGE`s the source `Component` (via
`resolve_component_ids`/`stub_component_id`, the same fallback
`semantic.py::_link_provenance` uses) and creates the Rule node plus its
`DERIVED_FROM` edge; the second re-`MATCH`es the just-created Rule by its
`(component, statement)` natural key and, only if a `Field` edits that
same component, creates the `GOVERNS` edge.

## get_rules

Every `Rule` with its source `Component`'s `(page_url, path)`, ordered by
`(page_url, path, statement)`. Rebuilt into the same `SemanticRule` shape
`build_rules` produces, same round-trip property `get_screens`/`get_flows`
maintain for their own semantic types.

## get_rule_field_entities

Every `Rule` whose `GOVERNS` edge resolved to a real `Field` and that
`Field`'s owning `Entity` - `[{"page_url", "path", "statement", "field",
"entity"}, ...]`. The shape `generators/requirements.py`'s
`_rule_based_requirements` (issue #203) needs to text- and link- a
Rule-based requirement, without threading raw Cypher into a generator -
the same dict-row convention `named_queries.py::callers_of` uses.
`GOVERNS` is best-effort (`_write_rule`'s own docstring): a Rule whose
`GOVERNS` edge never resolved simply doesn't appear here, the same
silent-absence stance the writer itself takes.
